import os
import json
from datetime import datetime
import folder_paths
import execution
import threading
import time

# --- CONFIGURATION ---
VERBOSE = True
FORCE_SAVE_TIMEOUT = 86400 
MATCH_TOLERANCE_SECONDS = 10 

# --- Log Folders ---
SUCCESS_DIR = os.path.join(folder_paths.get_input_directory(), "workflow_logs_success")
FAILED_DIR = os.path.join(folder_paths.get_input_directory(), "workflow_logs_failed")
os.makedirs(SUCCESS_DIR, exist_ok=True)
os.makedirs(FAILED_DIR, exist_ok=True)

# --- Global Dictionaries ---
active_workflows = {}
workflow_start_times = {}
log_lock = threading.Lock()

def find_latest_output_image(tolerance_seconds):
    try:
        output_dir = folder_paths.get_output_directory()
        now = time.time()
        candidate_files = []
        for filename in os.listdir(output_dir):
            filepath = os.path.join(output_dir, filename)
            if os.path.isdir(filepath): continue
            mtime = os.path.getmtime(filepath)
            if (now - mtime) <= tolerance_seconds:
                candidate_files.append((mtime, filename))
        if candidate_files:
            candidate_files.sort(key=lambda x: x[0], reverse=True)
            if VERBOSE: print(f"[AutoLogWorkflow] Match found via file search: {candidate_files[0][1]}")
            return candidate_files[0][1]
    except Exception as e:
        print(f"[AutoLogWorkflow] Error during output file search: {e}")
    return None

def get_output_filenames_from_data(outputs):
    filenames = []
    if not isinstance(outputs, dict): return filenames
    actual_outputs = outputs.get('outputs', outputs)
    for node_output in actual_outputs.values():
        if isinstance(node_output, dict) and 'images' in node_output:
            for image in node_output['images']:
                if isinstance(image, dict) and 'filename' in image and image.get('type') == 'output':
                    filenames.append(image['filename'])
    return filenames

def convert_prompt_to_workflow_format(prompt_data, extra_data=None):
    """Converts prompt data to ComfyUI workflow format"""
    try:
        # The base workflow comes from the prompt
        workflow = {
            "last_node_id": 0,
            "last_link_id": 0,
            "nodes": [],
            "links": [],
            "groups": [],
            "config": {},
            "version": 0.4
        }
        
        # If we have extra_data and it contains workflow_api, we try to extract more detailed information
        if extra_data and "extra_pnginfo" in extra_data:
            pnginfo = extra_data["extra_pnginfo"]
            if "workflow" in pnginfo:
                # We have the full workflow in the PNG metadata
                try:
                    original_workflow = json.loads(pnginfo["workflow"]) if isinstance(pnginfo["workflow"], str) else pnginfo["workflow"]
                    if isinstance(original_workflow, dict):
                        workflow.update(original_workflow)
                        if VERBOSE: print("[AutoLogWorkflow] Full workflow extracted from PNG metadata")
                        return workflow
                except:
                    pass
        
        # Fallback: we reconstruct the workflow from the prompt data
        node_id = 1
        link_id = 1
        
        for node_key, node_data in prompt_data.items():
            if not isinstance(node_data, dict):
                continue
                
            class_type = node_data.get("class_type", "Unknown")
            inputs = node_data.get("inputs", {})
            
            # Create the node in ComfyUI format
            node = {
                "id": node_id,
                "type": class_type,
                "pos": [200 + (node_id * 50), 200 + (node_id * 50)],  # Approximate position
                "size": {"0": 315, "1": 262},
                "flags": {},
                "order": node_id - 1,
                "mode": 0,
                "inputs": [],
                "outputs": [],
                "properties": {"Node name for S&R": f"{class_type}_{node_id}"}
            }
            
            # Map widgets and connections
            widgets_values = []
            input_connections = []
            
            for input_name, input_value in inputs.items():
                if isinstance(input_value, list) and len(input_value) == 2:
                    # It's a connection [node_id, output_index]
                    source_node = input_value[0]
                    source_output = input_value[1]
                    
                    input_connections.append({
                        "name": input_name,
                        "type": "*",
                        "link": link_id,
                        "slot_index": len(input_connections)
                    })
                    
                    # Create the link
                    workflow["links"].append([
                        link_id,           # link_id
                        int(source_node),  # origin_id
                        source_output,     # origin_slot
                        node_id,          # target_id
                        len(input_connections) - 1  # target_slot
                    ])
                    
                    link_id += 1
                else:
                    # It's a widget value
                    widgets_values.append(input_value)
            
            node["inputs"] = input_connections
            node["widgets_values"] = widgets_values
            
            # Add the node
            workflow["nodes"].append(node)
            
            if node_id > workflow["last_node_id"]:
                workflow["last_node_id"] = node_id
            
            node_id += 1
        
        workflow["last_link_id"] = link_id - 1
        
        if VERBOSE: print(f"[AutoLogWorkflow] Workflow reconstructed with {len(workflow['nodes'])} nodes")
        return workflow
        
    except Exception as e:
        print(f"[AutoLogWorkflow] Error in workflow conversion: {e}")
        # In case of error, return at least the original prompt
        return {
            "version": 0.4,
            "nodes": [],
            "links": [],
            "groups": [],
            "config": {},
            "raw_prompt": prompt_data
        }

def log_workflow_completion(prompt_id, full_outputs=None, success=True, error_msg="", force=False):
    with log_lock:
        if prompt_id not in active_workflows:
            return

        workflow_data = active_workflows.pop(prompt_id)
        if prompt_id in workflow_start_times:
            del workflow_start_times[prompt_id]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = SUCCESS_DIR if success else FAILED_DIR
        found_filename = None
        
        output_filenames = get_output_filenames_from_data(full_outputs)
        if output_filenames:
            found_filename = output_filenames[0]
            if VERBOSE: print("[AutoLogWorkflow] Filename obtained from direct outputs.")
        
        if not found_filename:
            if VERBOSE: print("[AutoLogWorkflow] No file in outputs, starting search on disk...")
            found_filename = find_latest_output_image(MATCH_TOLERANCE_SECONDS)

        if found_filename:
            filename_base = f"{found_filename}-_-{timestamp}"
        else:
            filename_base = f"workflow_{timestamp}_{prompt_id[:8]}"
        
        filename = os.path.join(folder, f"{filename_base}.json")
        
        # Convert the prompt to the ComfyUI workflow format
        comfyui_workflow = convert_prompt_to_workflow_format(
            workflow_data["prompt"], 
            workflow_data.get("extra_data")
        )
        
        # Add completion metadata
        comfyui_workflow["completion_info"] = {
            "timestamp": timestamp, 
            "success": success,
            "outputs": full_outputs.get('outputs', {}) if isinstance(full_outputs, dict) else {},
            "error": error_msg, 
            "forced_save": force,
            "filename_source": "direct_output" if output_filenames else ("disk_lookup" if found_filename else "none"),
            "prompt_id": prompt_id
        }
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(comfyui_workflow, f, indent=2, ensure_ascii=False)
        
        status_text = "SUCCESS" if success else "FAILED"
        force_text = " (FORCED)" if force else ""
        print(f"[AutoLogWorkflow] ==> Workflow {status_text}{force_text} saved: {os.path.basename(filename)}")

print("[AutoLogWorkflow] Initializing...")

original_execute = execution.PromptExecutor.execute
def logged_execute(self, prompt, prompt_id, extra_data, executed):
    try:
        workflow_data = {"prompt": prompt, "prompt_id": prompt_id, "extra_data": extra_data}
        with log_lock:
            active_workflows[prompt_id] = workflow_data
            workflow_start_times[prompt_id] = time.time()
        if VERBOSE: print(f"[AutoLogWorkflow] ✓ Execution started for {prompt_id}.")
    except Exception as e:
        print(f"[AutoLogWorkflow] Error in logged_execute: {e}")
    try:
        return original_execute(self, prompt, prompt_id, extra_data, executed)
    except Exception as e:
        print(f"[AutoLogWorkflow] Execution failed with exception for {prompt_id}: {e}")
        log_workflow_completion(prompt_id, None, False, str(e))
        raise
execution.PromptExecutor.execute = logged_execute
print("[AutoLogWorkflow] Hook on PromptExecutor.execute activated.")

original_task_done = execution.PromptQueue.task_done
def logged_task_done(self, *args, **kwargs):
    prompt_id = None
    try:
        status_obj = kwargs.get('status')
        if status_obj and hasattr(status_obj, 'messages'):
            for _, msg_data in status_obj.messages:
                if 'prompt_id' in msg_data:
                    prompt_id = msg_data['prompt_id']
                    break
        if not prompt_id: return original_task_done(self, *args, **kwargs)
        outputs_data = args[1] if len(args) > 1 else {}
        success = status_obj.status_str == 'success' if hasattr(status_obj, 'status_str') else False
        error_msg = "" if success else f"Final status: {getattr(status_obj, 'status_str', 'unknown')}"
        log_workflow_completion(prompt_id, outputs_data, success, error_msg)
    except Exception as e:
        print(f"[AutoLogWorkflow] Error in logged_task_done: {e}")
    return original_task_done(self, *args, **kwargs)
execution.PromptQueue.task_done = logged_task_done
print("[AutoLogWorkflow] Hook on PromptQueue.task_done activated.")

def force_save_monitor():
    while True:
        time.sleep(300) 
        try:
            with log_lock:
                current_time = time.time()
                workflows_to_save = [
                    pid for pid, start_time in workflow_start_times.items()
                    if (current_time - start_time) > FORCE_SAVE_TIMEOUT
                ]
            for prompt_id in workflows_to_save:
                print(f"[AutoLogWorkflow] Forcing save of {prompt_id} due to timeout ({FORCE_SAVE_TIMEOUT}s)")
                log_workflow_completion(prompt_id, None, True, "Timeout - auto-saved", force=True)
        except Exception as e:
            print(f"[AutoLogWorkflow] Error in the force-save monitor: {e}")
monitor_thread = threading.Thread(target=force_save_monitor, daemon=True)
monitor_thread.start()
print(f"[AutoLogWorkflow] System active. Save timeout: {FORCE_SAVE_TIMEOUT}s. File search window: {MATCH_TOLERANCE_SECONDS}s.")

# --- ADD THESE LINES TO MAKE IT A REAL CUSTOM NODE ---
class AutoLogWorkflow:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}
    
    RETURN_TYPES = ()
    FUNCTION = "do_nothing"
    CATEGORY = "utility"
    
    def do_nothing(self):
        return ()

NODE_CLASS_MAPPINGS = {
    "AutoLogWorkflow": AutoLogWorkflow
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AutoLogWorkflow": "Auto Log Workflow"
}