import json
import boto3
import os
import utils
import re
from datetime import datetime, timezone

DYNAMO_VIDEO_TASK_TABLE = os.environ.get("DYNAMO_VIDEO_TASK_TABLE")
DYNAMO_VIDEO_FRAME_TABLE = os.environ.get("DYNAMO_VIDEO_FRAME_TABLE")

def lambda_handler(event, context):
    task_id = event["Request"].get("TaskId")
    if task_id is None:
        return {
            "Error": "Invalid Request"
        }

    # Get video task from DB
    task = utils.dynamodb_get_by_id(table_name=DYNAMO_VIDEO_TASK_TABLE, id=task_id, key_name="Id")
    task["Status"] = "extraction_completed"
    task["ExtractionCompleteTs"] = datetime.now(timezone.utc).isoformat()

    agg_result = event["Request"]["ExtractionSetting"].get("AggregateResult", True)
    if agg_result:
        
        # Get frames from DB
        frames = utils.get_items_by_sort_key(DYNAMO_VIDEO_FRAME_TABLE, task_id)
        
        agg_result = {
            "DetectLabelAgg": [],
            "DetectLabelCategoryAgg": [],
            "DetectTextAgg": [],
            "DetectModerationAgg": [],
            "DetectCelebrityAgg": []
        }
        
        for frame in frames:
            ts = float(frame["timestamp"])
            if "detect_label" in frame and len(frame["detect_label"]) > 0:
                for l in frame["detect_label"]:
                    agg_result["DetectLabelAgg"] = add_to_list(l["name"], ts, agg_result["DetectLabelAgg"])
                    if "categories" in l:
                        for cat in l["categories"]:
                            agg_result["DetectLabelCategoryAgg"] = add_to_list(cat, ts, agg_result["DetectLabelCategoryAgg"])
                
                agg_result["DetectLabelAgg"] = sort_list(agg_result["DetectLabelAgg"])
                agg_result["DetectLabelCategoryAgg"] = sort_list(agg_result["DetectLabelCategoryAgg"])
                
            if "detect_text" in frame and len(frame["detect_text"]) > 0:
                for l in frame["detect_text"]:
                    agg_result["DetectTextAgg"] = add_to_list(l["name"], ts, agg_result["DetectTextAgg"])
                agg_result["DetectTextAgg"] = sort_list(agg_result["DetectTextAgg"])
                    
            if "detect_moderation" in frame and len(frame["detect_moderation"]) > 0:
                for l in frame["detect_moderation"]:
                    agg_result["DetectModerationAgg"] = add_to_list(l["name"], ts, agg_result["DetectModerationAgg"])
                agg_result["DetectModerationAgg"] = sort_list(agg_result["DetectModerationAgg"])
                    
            if "detect_celebrity" in frame and len(frame["detect_celebrity"]) > 0:
                for l in frame["detect_celebrity"]:
                    agg_result["DetectCelebrityAgg"] = add_to_list(l["name"], ts, agg_result["DetectCelebrityAgg"])
                agg_result["DetectCelebrityAgg"] = sort_list(agg_result["DetectCelebrityAgg"])
        
        task["AggResult"] = agg_result
        
    # Save aggregated results to DB
    utils.dynamodb_table_upsert(DYNAMO_VIDEO_TASK_TABLE, task)

    return {
        'statusCode': 200,
        'body': event
    }

def add_to_list(item_name, ts, agg_list):
    for i in agg_list:
        if i["name"] == item_name:
            if ts not in i["timestamps"]:
                i["timestamps"].append(ts)
            return agg_list
            
    agg_list.append({"name": item_name, "timestamps": [ts]})
    return agg_list

def sort_list(agg_list):
    if not agg_list or len(agg_list) == 0:
        return agg_list
    
    for item in agg_list:
        item["timestamps"] = sorted(item["timestamps"], reverse=False)
    
    return agg_list
