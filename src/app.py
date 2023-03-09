# authelia string consts to read from labels
CONST_AUTHELIA_STRING="authelia"
CONST_ACCESS_POLICY_STRING="access_policy"

CONST_DOMAIN_STRING="domain"
CONST_POLICY_STRING="policy"
CONST_SUBJECT_STRING="subject"
CONST_METHODS_STRING="methods"
CONST_NETWORKSS_STRING="networks"
CONST_RESOURCESS_STRING="resources"
CONST_QUERY_STRING="query"

# authelia policy options restrictions
CONST_POLICY_OPTIONS=["bypass", "one_factor", "two_factor"]

# traefik string consts to read from labels and traefik api
CONST_TRAEFIK_STRING="traefik"
CONST_HTTP_STRING="http"
CONST_ROUTERS_STRING="routers"
CONST_RULE_STRING="rule"

# file write constants
CONST_ACCESS_CONTROL_STRING="access_control"
CONST_RULES_STRING="rules"

# formatting
CONST_INDENT_LEN=2

CONST_DOMAIN_STRING_PATTERN="[\w*|.]*"

# --authelia.access_policy.[name].domain= auto-genned
# --authelia.access_policy.[name].domain_regex

# --authelia.access_policy.[name].policy=bypass|one_factor|two_factor
# --authelia.access_policy.[name].subject # defined zero to multiple "" or ["",""]
# --authelia.access_policy.[name].methods=
# --authelia.access_policy.[name].networks
# --authelia.access_policy.[name].resources
# --authelia.access_policy.[name].query

import os
import docker
import time
import requests
import re

def query_traefik_router_domain(TRAEFIK_HOST, traefik_router):
    
    url = TRAEFIK_HOST+"/api/http/routers/" + traefik_router + "@docker"
    print("Trying to get details from traefik: ", url)
    response = requests.get(url)
    if response.status_code == 200:
        json = response.json()
        if CONST_RULE_STRING in json:
            rule = json[CONST_RULE_STRING]
            print("Reading rule:", rule)
            host = re.compile("Host\(."+CONST_DOMAIN_STRING_PATTERN+".\)").findall(rule)[0]
            print("Got Host string from traefik:", host)
            domain = re.compile(CONST_DOMAIN_STRING_PATTERN).findall(host)[0]

            print("Converted rule to domain:", domain)
            return domain
    return None

def run(labels, TRAEFIK_HOST):

    traefik_router = None

    groupings = {}
    for _label_name,label_value in labels.items():
        label_parts = _label_name.lower().split(".")
        if label_parts[0] == CONST_TRAEFIK_STRING and label_parts[1] == CONST_HTTP_STRING and label_parts[2] == CONST_ROUTERS_STRING:
            traefik_router = label_parts[3]

        if label_parts[0] == CONST_AUTHELIA_STRING and label_parts[1] == CONST_ACCESS_POLICY_STRING:
            current_group = groupings.get(label_parts[2], {})

            if label_parts[3] == CONST_DOMAIN_STRING:
                current_group[CONST_DOMAIN_STRING] = label_value
            if label_parts[3] == CONST_POLICY_STRING:
                if label_value in CONST_POLICY_OPTIONS:
                    current_group[CONST_POLICY_STRING] = label_value

            elif label_parts[3] == CONST_SUBJECT_STRING:
                if CONST_SUBJECT_STRING not in current_group:
                    groupings[label_parts[2]][CONST_SUBJECT_STRING] = []
                current_group[CONST_SUBJECT_STRING].append(label_value)
            #elif label_parts[2].startswith(CONST_METHODS_STRING):
            #    methods.append(label_value)
            #elif label_parts[2].startswith(CONST_NETWORKSS_STRING):
            #    networks.append(label_value)
            #elif label_parts[2].startswith(CONST_RESOURCESS_STRING):
            #    resources.append(label_value)
            #elif label_parts[2].startswith(CONST_QUERY_STRING):
            #    query.append(label_value)
            else:
                print(label_parts[3], "is not a valid option (yet)")

            groupings[label_parts[2]] = current_group
    
    
    for grouping in groupings.values(): 
        if CONST_DOMAIN_STRING not in grouping:
            grouping[CONST_DOMAIN_STRING] = "";
            if TRAEFIK_HOST is not None:
                result = query_traefik_router_domain(TRAEFIK_HOST, traefik_router)
                if result is not None: 
                    grouping[CONST_DOMAIN_STRING] = result;

    return groupings
    


def write_to_file(domain_rules, file):
    file_contents = []
    file_contents.append(CONST_ACCESS_CONTROL_STRING + ":")
    file_contents.append("".rjust(CONST_INDENT_LEN) + (CONST_RULES_STRING + ":"))
    for group_name,rules in domain_rules.items():
        
        file_contents.append("".rjust((CONST_INDENT_LEN * 3) - 2) + ("# " + group_name))
        file_contents.append("".rjust((CONST_INDENT_LEN * 3) - 2) + ("- " + CONST_DOMAIN_STRING + ": " + "\"" + rules[CONST_DOMAIN_STRING] + "\""))
        file_contents.append("".rjust( CONST_INDENT_LEN * 3     ) + (CONST_POLICY_STRING + ": " + rules[CONST_POLICY_STRING]))

        if CONST_SUBJECT_STRING in rules and rules[CONST_SUBJECT_STRING]:            
            file_contents.append("".rjust(CONST_INDENT_LEN * 3) + (CONST_SUBJECT_STRING + ":"))
            for subject in rules[CONST_SUBJECT_STRING]: 
                file_contents.append("".rjust(CONST_INDENT_LEN * 3) + ("- " + subject))
                
    with open(file, "w") as _file:
        for line in file_contents:
            _file.write(line+"\r\n")
    print("Final Config: ")
    with open(file, "r") as _file:
        print(_file.read())

def main():
        
    ENABLE_DOCKER_SWARM = os.environ.get('DOCKER_SWARM', False)
    DOCKER_HOST = os.environ.get('DOCKER_HOST', "unix://var/run/docker.sock")
    TRAEFIK_HOST = os.environ.get("TRAEFIK_HOST", None)
    FILE_NAME = os.environ.get("FILE_NAME", "authelia_config.yml")
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

    print("Starting...")

    full_config={}
    list_of_containers_or_services = api.services() if ENABLE_DOCKER_SWARM else api.containers()
    for container in list_of_containers_or_services:
        labels = container["Spec"]["Labels"] if ENABLE_DOCKER_SWARM else container["Labels"]
        result = run(labels, TRAEFIK_HOST)
        if result is not None:
            full_config.update(result)
    write_to_file(full_config, "/generated_config/"+FILE_NAME)


main()
