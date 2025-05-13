
import json
import re
import time
import requests
from retrying import retry
import sys

PUBLISH_TIMEOUT = 1200
UPLOAD_TIMEOUT = 60
UPLOADED_STATUS = "uploaded"
VALIDATED_STATUS = "validated"
FAILED_STATUS = "failed"

def log(s):
    print(s)
    sys.stdout.flush()


def log_r(s):
    log(f"""\033[31m {s} \033[0m""")


def log_g(s):
    log(f"""\033[1;32m {s} \033[0m""")

def upload_artifact_file(artifact_file_path, portal_token):
    start_index = artifact_file_path.rfind('/') + 1
    end_index = artifact_file_path.rfind('.zip')
    url = f"https://central.sonatype.com/api/v1/publisher/upload?name={artifact_file_path[start_index:end_index]}"
    files = {
        'bundle': (artifact_file_path, open(artifact_file_path, 'rb'))
    }
    headers = {
        "Authorization": f"Bearer {portal_token}"
    }
    response = requests.post(url, headers=headers, files=files)
    return response.text

@retry(stop_max_attempt_number=3)
def query_status(query_id, portal_token):
    headers = {
        "Authorization": f"Bearer {portal_token}"
    }
    response = requests.post(f"https://central.sonatype.com/api/v1/publisher/status?id={query_id}", headers=headers)
    match = re.search(r'"deploymentState":"([^"]*)', response.text)
    if match:
        deployment_state = match.group(1)
        return deployment_state, response.text
    else:
        raise Exception(f"Error: deploymentState not found in the response: {response.text}")

def publish_artifact(query_id, portal_token):
    headers = {
        "Authorization": f"Bearer {portal_token}"
    }
    requests.post(f"https://central.sonatype.com/api/v1/publisher/deployment/{query_id}", headers=headers)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        log_r("Usage: python publish.py portal_token <artifact_file_path>")
        sys.exit(1)
    portal_token = sys.argv[1]
    try:
        artifact_file_path_list = json.loads(sys.argv[2])
    except Exception as e:
        log_r(f"Error parsing artifact_path_list parameter ({sys.argv[2]}): {e}")
        exit(1)
    query_status_dict = {}
    query_id_dict = {}
    log("Start uploading...")
    for artifact_file_path in artifact_file_path_list:
        log(f"Uploading {artifact_file_path}...")
        query_id = upload_artifact_file(artifact_file_path, portal_token)
        query_status_dict[query_id] = UPLOADED_STATUS
        query_id_dict[query_id] = artifact_file_path
    log(f"upload finish! query_status_dict: {query_status_dict} query_id_dict: {query_id_dict}")
    poll_interval = 5
    max_polls=UPLOAD_TIMEOUT // poll_interval
    poll_count = 0
    
    while query_status_dict and poll_count < max_polls:
        query_id_list = list(query_status_dict.keys())[:]
        for query_id in query_id_list:
            status, response = query_status(query_id, portal_token)
            if status == "VALIDATED":
                log_g(f"Upload {query_id_dict[query_id]} success")
                del query_status_dict[query_id]
            elif status == "FAILED":
                query_status_dict[query_id] = FAILED_STATUS
                log_r(f"Error: upload failed, artifact_path: {query_id_dict[query_id]} response: {response}")
                sys.exit(1)
            else:
                print(f"Uploading {query_id_dict[query_id]} {status}")
        poll_count += 1
        time.sleep(poll_interval)
    if query_status_dict:
        log_r(f"Error: upload timeout! UnFinished artifacts: {[query_id_dict[key] for key, _ in query_status_dict.items()]}")
        sys.exit(1)
    log_g("Upload success!")
    log("Start publishing...")
    query_status_dict = {}
    for query_id in query_id_dict.keys():
        query_status_dict[query_id] = VALIDATED_STATUS
        print(f"Publishing {query_id_dict[query_id]}")
        publish_artifact(query_id, portal_token)

    max_polls=PUBLISH_TIMEOUT // poll_interval
    poll_count = 0
    while query_status_dict and poll_count < max_polls:
        query_id_list = list(query_status_dict.keys())[:]
        for query_id in query_id_list:
            status, response = query_status(query_id, portal_token)
            if status == "PUBLISHED":
                del query_status_dict[query_id]
            elif status == "FAILED":
                query_status_dict[query_id] = FAILED_STATUS
                log_r(f"Error: publish failed, artifact_path: {query_id_dict[query_id]} response: {response}")
                sys.exit(1)
            else:
                print(f"Publishing {query_id_dict[query_id]} {status}")
        poll_count += 1
        time.sleep(poll_interval)
    if query_status_dict:
        log_r(f"Error: publish timeout! UnFinished artifacts: {[query_id_dict[key] for key, _ in query_status_dict.items()]}")
        sys.exit(1)
    else:
        log_g("Publish success!")
        