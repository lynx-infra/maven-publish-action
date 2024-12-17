#!/bin/bash
API_KEY=$1
API_PASSWORD=$2
ARTIFACT_PATH=$3

PUBLISH_TIMEOUT=1200
UPLOAD_TIMEOUT=60

echo "API_KEY: $API_KEY"
echo "API_PASSWORD: $API_PASSWORD"
echo "ARTIFACT_PATH: $ARTIFACT_PATH"

token=$(printf "$API_KEY:$API_PASSWORD" | base64)

echo "token: $token"

query_id=$(curl --request POST \
          --verbose \
          --header "Authorization: Bearer $token" \
          --form bundle=@$ARTIFACT_PATH \
          https://central.sonatype.com/api/v1/publisher/upload)

status=""
query_response=""

query_status() {
    local timeout=$1
    shift 1
    local target_status=("$@")
    local poll_interval=5
    local max_polls=$((timeout / poll_interval))
    local poll_count=0
    while [ $poll_count -lt $max_polls ]
    do
        response=$(curl --request POST \
                    --verbose \
                    --header "Authorization: Bearer $token" \
                    "https://central.sonatype.com/api/v1/publisher/status?id=$query_id")
        deployment_state=$(echo "$response" | grep -o '"deploymentState":"[^"]*' | sed 's/"deploymentState":"//')
        if [ -z "$deployment_state" ]; then
            echo "Error: deploymentState not found in the response: $response"
            exit 1
        fi
        if [[ " ${target_status[@]} " =~ " ${deployment_state} " ]]; then
            status=$deployment_state
            query_response=$response
            break
        fi
        ((poll_count++))
        echo "Polling... (Poll count: $poll_count)"    
        sleep $poll_interval
    done
}

upload_timeout=30
status_array=("VALIDATED" "FAILED")
query_status $upload_timeout "${status_array[@]}"

echo "Upload Status: $status"

if [ "$status" = "VALIDATED" ]
then
    curl --request POST \
        --verbose \
        --header "Authorization: Bearer $token" \
        "https://central.sonatype.com/api/v1/publisher/deployment/$query_id"

    publish_timeout=1000
    status_array=("PUBLISHED" "FAILED")
    query_status $publish_timeout "${status_array[@]}"
    echo "Publish Status: $status"
    if [ "$status" = "PUBLISHED" ]
    then
        echo "Success: Publish Success!"
        exit 0
    fi
    if [ "$status" = "FAILED" ]
    then
        echo "Error: Publish Failed! $query_response"
        exit 1
    fi
fi

if [ "$status" = "FAILED" ]
then
    echo "Error: Publish Failed! $query_response"
    exit 1
fi

if [ "$status" = "" ]
then
    echo "Error: Publish Timeout!"
    exit 1
fi