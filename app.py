import os
import random
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from core import (
    DiscordAPI, 
    StatelessQuestCompleter, 
    fetch_latest_build_number, 
    get_quest_name, 
    get_task_type, 
    get_seconds_needed, 
    get_seconds_done,
    is_enrolled, 
    is_completed, 
    is_completable, 
    is_expired
)

app = Flask(__name__)
CORS(app)

CACHE_TTL = 600
cached_build_number = None
last_fetched_time = 0

def get_build_number():
    global cached_build_number, last_fetched_time
    current_time = time.time()
    
    if not cached_build_number or (current_time - last_fetched_time > CACHE_TTL):
        try:
            cached_build_number = fetch_latest_build_number(lambda msg, level: None)
            last_fetched_time = current_time
        except Exception:
            if not cached_build_number:
                cached_build_number = 123456
    return cached_build_number

@app.route("/")
def index():
    return jsonify({"status": "API is running", "service": "Discord Quest API"}), 200

@app.route("/api/quest/init", methods=["POST"])
def init_quest():
    try:
        data = request.json or {}
        token = data.get("token")
        if not token:
            return jsonify({"error": "Token is required", "status": "error"}), 400

        build_number = get_build_number()
        api = DiscordAPI(token, build_number, lambda msg, level: None)
        
        if not api.validate_token():
            return jsonify({"error": "Token không hợp lệ", "status": "error"}), 401

        completer = StatelessQuestCompleter(api)
        quests = completer.fetch_quests()
        
        enrolled_any = False
        for q in quests:
            if not is_enrolled(q) and not is_completed(q) and is_completable(q) and not is_expired(q):
                completer.enroll_quest(q)
                enrolled_any = True
                
        if enrolled_any:
            quests = completer.fetch_quests()
            
        quest_list = []
        active_quest_data = None
        for q in quests:
            t_type = get_task_type(q)
            if not t_type:
                continue
            q_name = get_quest_name(q)
            q_needed = get_seconds_needed(q)
            q_done = get_seconds_done(q)
            q_completed = is_completed(q)
            
            if not active_quest_data and not q_completed and is_completable(q) and not is_expired(q):
                pid = random.randint(1000, 30000)
                stream_key = f"call:0:{pid}" if "DESKTOP" in t_type else "call:0:1"
                active_quest_data = {
                    "id": q["id"],
                    "name": q_name,
                    "task_type": t_type,
                    "needed": q_needed,
                    "done": q_done,
                    "stream_key": stream_key
                }
                
            quest_list.append({
                "id": q["id"],
                "name": q_name,
                "task_type": t_type,
                "needed": q_needed,
                "done": q_done,
                "completed": q_completed
            })
            
        return jsonify({
            "status": "active" if active_quest_data else "no_quests",
            "quest": active_quest_data,
            "quests": quest_list
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route("/api/quest/progress_video", methods=["POST"])
def progress_video():
    try:
        data = request.json or {}
        token = data.get("token")
        qid = data.get("id")
        timestamp = data.get("timestamp")
        
        if not token or not qid or timestamp is None:
            return jsonify({"error": "Missing params"}), 400
            
        build_number = get_build_number()
        api = DiscordAPI(token, build_number, lambda msg, level: None)
        completer = StatelessQuestCompleter(api)
        
        res = completer.send_video_progress(qid, timestamp)
        completed = bool(res.get("completed_at"))
        
        return jsonify({
            "status": "ok",
            "completed": completed
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route("/api/quest/heartbeat", methods=["POST"])
def progress_heartbeat():
    try:
        data = request.json or {}
        token = data.get("token")
        qid = data.get("id")
        stream_key = data.get("stream_key")
        task_type = data.get("task_type")
        
        if not token or not qid or not stream_key or not task_type:
            return jsonify({"error": "Missing params"}), 400
            
        build_number = get_build_number()
        api = DiscordAPI(token, build_number, lambda msg, level: None)
        completer = StatelessQuestCompleter(api)
        
        res = completer.send_heartbeat(qid, stream_key, terminal=False)
        
        completed = bool(res.get("completed_at"))
        new_done = -1
        pd = res.get("progress", {})
        if pd and task_type in pd:
            new_done = pd[task_type].get("value", -1)
            
        return jsonify({
            "status": "ok",
            "completed": completed,
            "done": new_done
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
