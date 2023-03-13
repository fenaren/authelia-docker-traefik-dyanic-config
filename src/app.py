import os
import docker
import requests
import re
# authelia string consts to read from labels
CONST_AUTHELIA_STRING="authelia"

CONST_ACCESS_POLICY_STRING="access_policy"

CONST_DOMAIN_STRING="domain"
CONST_DOMAIN_REGEX_STRING="domain_regex"
CONST_QUERY_STRING="query"
CONST_DETECT_STRING="detect"
CONST_PRIORITY_STRING="priority"

# authelia policy options restrictions
CONST_POLICY_OPTIONS=["bypass", "one_factor", "two_factor"]
CONST_AUTHORIZATION_POLICY_OPTIONS=[CONST_POLICY_OPTIONS[1], CONST_POLICY_OPTIONS[2]]
CONST_CONSENT_MODE_OPTIONS=["auto", "explicit", "implicit", "pre-configured"]

# traefik string consts to read from labels and traefik api
CONST_TRAEFIK_ROUTER_STRING="traefik_router"
CONST_HTTP_STRING="http"
CONST_ROUTERS_STRING="routers"
CONST_RULE_STRING="rule"

# file write constants
CONST_ACCESS_CONTROL_STRING="access_control"
CONST_RULES_STRING="rules"

# formatting
CONST_INDENT_LEN=2


def query_traefik_router_domain(TRAEFIK_HOST:str, traefik_router_name:str):
    if TRAEFIK_HOST is None: 
        return None
    url = (TRAEFIK_HOST if "http" in TRAEFIK_HOST else "http://" + TRAEFIK_HOST)+":8080" +"/api/http/routers/" + traefik_router_name + "@docker"
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


def extract_array_from_string(string_to_check:str):
    array_check = re.search("(?P<label>(:.|[^\.])*)\[(?P<index>\d+)\]$", string_to_check)
    if array_check is not None:
        # has an array
        label_part_without_array = array_check.group("label")
        label_part_index = (int)(array_check.group("index"))
        return label_part_without_array, label_part_index
    return  string_to_check, -1


def array(current_data_structure, name:str, index:int):
    # tries to get an existing array from 'current_data_structure'
    # if that array doesnt exist, create one of index size
    next_structure = current_data_structure.get(name, [None] * (index + 1))
    # if that array is smaller than index, append until meets size
    if len(next_structure) <= index:
        next_structure.extend([None] * (index + 1 - len(next_structure)))
    return next_structure


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

    
def process_labels(labels):
    grouping = {}
    for label_name, label_value in labels.items(): #iterate label ITEMS (gets K,V pair)
        label_parts = label_name.lower().split(".") #split into array 
        if label_parts[0] == CONST_AUTHELIA_STRING:  # check if relevant / filter #TODO should check before split?
            label_name, label_array_index = extract_array_from_string(label_parts[2])
            if label_array_index != -1:
                next_structure = array(grouping, label_name, label_array_index)
                inner_structure = {} if next_structure[label_array_index] is None else next_structure[label_array_index]
                result = recurse(inner_structure, label_parts, label_value, 3)
                next_structure[label_array_index] = result
                grouping[label_name] = next_structure
            else:
                # if not array, just set it 
                result = recurse({}, label_parts, label_value, 3)
                inner = grouping.get(label_parts[2], {})
                grouping[label_parts[2]] = inner
                inner.update(result)
    return grouping


def post_process_single(TRAEFIK_HOST, entry):
    if CONST_DOMAIN_STRING in entry and CONST_TRAEFIK_ROUTER_STRING in entry[CONST_DOMAIN_STRING]:
        traefik_router_name = entry[CONST_DOMAIN_STRING][CONST_TRAEFIK_ROUTER_STRING]
        domain = query_traefik_router_domain(TRAEFIK_HOST, traefik_router_name)
        entry[CONST_DOMAIN_STRING] = ""
        if domain is not None:
            entry[CONST_DOMAIN_STRING] = domain


def post_process(TRAEFIK_HOST:str, groupings):
    file_yaml = []
    for grouping_name,grouping_value in groupings.items():
        if isinstance(grouping_value, list):
            for entry in grouping_value:
                post_process_single(TRAEFIK_HOST, entry)
                file_yaml.append(entry)
        else:
            post_process_single(TRAEFIK_HOST, grouping_value)
            file_yaml.append(grouping_value)
    return {CONST_ACCESS_CONTROL_STRING: file_yaml}


def write_to_file(file_path, rules):
    import yaml
    with open(file_path, "w") as _file:
        _file.write(yaml.dump(rules))
    print("Final Config: ")
    print()
    with open(file_path, "r") as _file:
        print(_file.read())


def main(DOCKER_HOST = os.getenv('DOCKER_HOST', "unix://var/run/docker.sock"), ENABLE_DOCKER_SWARM = os.getenv('DOCKER_SWARM', False), TRAEFIK_HOST = os.getenv("TRAEFIK_HOST", None), FILE_PATH = os.getenv("FILE_PATH", "/config/authelia_config.yml")):
    api = get_docker_api(DOCKER_HOST)
    groupings = {}
    list_of_containers_or_services = api.services() if ENABLE_DOCKER_SWARM else api.containers()
    for container in list_of_containers_or_services:
        labels = container["Spec"]["Labels"] if ENABLE_DOCKER_SWARM else container["Labels"]
        result = process_labels(labels)
        if result is not None:
            groupings.update(result)
    print(groupings)
    print()
    full_config = post_process(TRAEFIK_HOST, groupings)
    os.makedirs(os.path.dirname(FILE_PATH), exist_ok=True)
    write_to_file(FILE_PATH, full_config)
    #print()
    #return full_config


main()