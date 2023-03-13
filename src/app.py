import os
import docker
import requests
import re
# authelia string consts to read from labels
CONST_AUTHELIA_STRING="authelia"

CONST_DOMAIN_STRING="domain"
CONST_DOMAIN_REGEX_STRING="domain_regex"

# optional definition for traefik support 
CONST_TRAEFIK_ROUTER_STRING="traefik_router"

# traefik string consts to read from labels and traefik api
CONST_RULE_STRING="rule"

CONST_ACCESS_CONTROL_STRING="access_control"
CONST_IDENTITY_PROVIDERS_STRING="identity_providers"
CONST_OIDC_STRING = "oidc"
CONST_CLIENTS_STRING = "clients"


# TODO also return host regex rules too
# queries traefik api for a router and returns a host domain (if able)
def query_traefik_router_domain(TRAEFIK_HOST:str, traefik_router_name:str):
    if TRAEFIK_HOST is None: 
        return None
    url = (TRAEFIK_HOST if "http" in TRAEFIK_HOST else "http://" + TRAEFIK_HOST) + "/api/http/routers/" + traefik_router_name + "@docker"
    print("Trying to get details from traefik: ", url)
    response = requests.get(url)
    if response.status_code == 200:
        json = response.json()
        if CONST_RULE_STRING in json:
            rule = json[CONST_RULE_STRING]
            print("Reading rule:", rule)
            host = re.compile("Host\(.[\w*|.]*.\)").findall(rule)[0]
            print("Got Host string from traefik:", host)
            
            domain = host.replace('Host(', "")[1:-2]
            print("Converted rule to domain:", domain)
            return domain
    else:
        print("Error: Response was not 200 (OK)", response)
    return None

# retrieve the docker api, try 4 times with timeouts, if fail exit
def get_docker_api(DOCKER_HOST):
    import time
    api=None
    errors=0
    while errors <=3:
        try:
            api = docker.APIClient(base_url=DOCKER_HOST)
            if api is not None:
                break;
        except Exception as e:
            print("Encountered error, trying again to get docker API client...")
            print(e)
            errors+=1
            time.sleep(1)
    if api is None:
        print("Tried and failed to reach the docker API client after 4 tries. Cannot continue.")
        exit(1)
    return api


# Splits a string into two parts, first the name, second the array index
# eg 
#   test -> test,-1
#   test[4] -> test,4
def extract_array_from_string(string_to_check:str):
    array_check = re.search("(?P<label>(:.|[^\.])*)\[(?P<index>\d+)\]$", string_to_check)
    if array_check is not None:
        # has an array
        label_part_without_array = array_check.group("label")
        label_part_index = (int)(array_check.group("index"))
        return label_part_without_array, label_part_index
    return  string_to_check, -1


# needed to write this so that array indicies always stayed the same, unlike how .append would
def array(current_data_structure, name:str, index:int):
    # tries to get an existing array from 'current_data_structure'
    # if that array doesnt exist, create one of index size
    next_structure = current_data_structure.get(name, [None] * (index + 1))
    # if that array is smaller than index, append until meets size
    if len(next_structure) <= index:
        next_structure.extend([None] * (index + 1 - len(next_structure)))
    return next_structure


# iterate through the parts of the label and extract the data
def recurse(current_data_structure, label_parts, label_value:str, label_part_index:int = 0):
    # check if current label_part has an array identifier    
    label_name, label_array_index = extract_array_from_string(label_parts[label_part_index])
    if label_array_index != -1:
        next_structure = array(current_data_structure, label_name, label_array_index)
        if len(label_parts) > label_part_index + 1:
            inner_structure = {} if next_structure[label_array_index] is None else next_structure[label_array_index]
            result = recurse(inner_structure, label_parts, label_value, label_part_index + 1)
            next_structure[label_array_index] = result
            current_data_structure[label_name] = next_structure
            return current_data_structure
        else:
            next_structure[label_array_index] = label_value
            current_data_structure[label_name] = next_structure
            return current_data_structure
    # check if last element
    elif len(label_parts) > label_part_index + 1:
        # not last element
        # next data structure is dict
        next_structure = current_data_structure.get(label_name, {})
        result = recurse(next_structure, label_parts, label_value, label_part_index + 1)
        current_data_structure[label_name] = result
        return current_data_structure
    else:
        # last element
        current_data_structure[label_name] = label_value
        return current_data_structure

def get_inner_dict(outer_data_structure, label_parts, depth, start=0, final={}):
    current_data_structure = outer_data_structure
    for i in range(start, depth):
        grouping_inner = current_data_structure.get(label_parts[i], final if i == depth -1 else {})
        current_data_structure[label_parts[i]] = grouping_inner
        current_data_structure = grouping_inner
    return current_data_structure


# process label array, converting all labels into a pythonic data structure 
def process_labels(labels):
    grouping = {}
    for label_name, label_value in labels.items(): #iterate label ITEMS (gets K,V pair)
        label_parts = label_name.lower().split(".") #split into array 
        if label_parts[0] == CONST_AUTHELIA_STRING:  # check if relevant / filter #TODO should check before split?
            __name_index = 0
            if label_parts[1] == CONST_ACCESS_CONTROL_STRING:
                __name_index = 2
            elif label_parts[1] == CONST_IDENTITY_PROVIDERS_STRING and label_parts[2] == CONST_OIDC_STRING and label_parts[3] == CONST_CLIENTS_STRING:
                __name_index = 4
            label_name, label_array_index = extract_array_from_string(label_parts[__name_index])
            grouping_p1 = get_inner_dict(grouping, label_parts, __name_index, start=1, final={})
            if label_array_index != -1:
                # if array, merge to array of existing
                next_structure = array(grouping_p1, label_name, label_array_index)
                inner_structure = {} if next_structure[label_array_index] is None else next_structure[label_array_index]
                result = recurse(inner_structure, label_parts, label_value, __name_index + 1)
                next_structure[label_array_index] = result
                grouping_p1[label_name] = next_structure
            else:
                # if not array, merge to existing
                inner = grouping_p1.get(label_name, {})
                result = recurse(inner, label_parts, label_value, __name_index + 1)
                grouping_p1[label_name] = inner
    return grouping


# per entry, clean up the data for writing to file
def post_process_single(TRAEFIK_HOST, entry):
    # use traefik to find domain name 
    if CONST_DOMAIN_STRING in entry and CONST_TRAEFIK_ROUTER_STRING in entry[CONST_DOMAIN_STRING]:
        traefik_router_name = entry[CONST_DOMAIN_STRING][CONST_TRAEFIK_ROUTER_STRING]
        domain = query_traefik_router_domain(TRAEFIK_HOST, traefik_router_name)
        entry[CONST_DOMAIN_STRING] = ""
        if domain is not None:
            entry[CONST_DOMAIN_STRING] = domain


# clean up all the entries for writing to file
def post_process(TRAEFIK_HOST:str, groupings):
    file_yaml = {}
    for grouping_name,grouping_value in groupings.items():
        file_yaml_inner = None
        iteratable = None
        if grouping_name == CONST_IDENTITY_PROVIDERS_STRING and CONST_OIDC_STRING in grouping_value and CONST_CLIENTS_STRING in grouping_value[CONST_OIDC_STRING]:
            file_yaml_inner = get_inner_dict(file_yaml, [CONST_IDENTITY_PROVIDERS_STRING, CONST_OIDC_STRING, CONST_CLIENTS_STRING], 3, start=0,final=[])
            iteratable = grouping_value[CONST_OIDC_STRING][CONST_CLIENTS_STRING].values()
        elif grouping_name == CONST_ACCESS_CONTROL_STRING:
            file_yaml_inner = file_yaml.get(grouping_name, [])
            file_yaml[grouping_name] = file_yaml_inner
            iteratable = grouping_value.values()
        if file_yaml_inner is not None and iteratable is not None:
            for grouping_inner_value in iteratable:
                    if isinstance(grouping_inner_value, list):
                        for entry in grouping_inner_value:
                            post_process_single(TRAEFIK_HOST, entry)
                            file_yaml_inner.append(entry)
                    else:
                        post_process_single(TRAEFIK_HOST, grouping_inner_value)
                        file_yaml_inner.append(grouping_inner_value)
    return file_yaml


# writes the pythonic data structure to yaml file
def write_to_file(file_path, rules):
    import yaml
    with open(file_path, "w") as _file:
        _file.write(yaml.dump(rules))
    print("Final Config: ")
    print()
    with open(file_path, "r") as _file:
        print(_file.read())


def deep_merge(original, update):
    for key in original.keys():
        if key not in update:
            update[key] = original[key]
        elif key in update and isinstance(update[key], dict):
            deep_merge(original[key], update[key])
        else:
            update[key].update(original[key])


# gets all the envvars, gets the labels and writes all to file
def main(DOCKER_HOST = os.getenv('DOCKER_HOST', "unix://var/run/docker.sock"), ENABLE_DOCKER_SWARM = os.getenv('DOCKER_SWARM', False), TRAEFIK_HOST = os.getenv("TRAEFIK_HOST", None), FILE_PATH = os.getenv("FILE_PATH", "/config/configuration.yml")):
    api = get_docker_api(DOCKER_HOST)
    groupings = {}
    list_of_containers_or_services = api.services() if ENABLE_DOCKER_SWARM else api.containers()
    for container in list_of_containers_or_services:
        labels = container["Spec"]["Labels"] if ENABLE_DOCKER_SWARM else container["Labels"]
        result = process_labels(labels)
        if result is not None:
            deep_merge(result, groupings)
    full_config = post_process(TRAEFIK_HOST, groupings)
    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    write_to_file(FILE_PATH, full_config)


main()