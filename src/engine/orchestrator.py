import json
import subprocess
import os
import time
from src.engine.artifact_manager import ArtifactManager
from src.engine.pipeline import PipelineState
from src.core.database import log_audit

class AgentOrchestrator:
    def __init__(self, staging_dir="data/staging"):
        self.artifact_manager = ArtifactManager()
        self.staging_dir = staging_dir

    def request_human_verdict(self, session_id, artifact_type, content):
        """Создает файл-гейт и ждет вердикта пользователя."""
        session_path = os.path.join(self.staging_dir, session_id)
        os.makedirs(session_path, exist_ok=True)
        
        artifact_path = os.path.join(session_path, f"{artifact_type}.md")
        verdict_path = os.path.join(session_path, f"{artifact_type}_verdict.json")
        
        with open(artifact_path, "w") as f:
            f.write(content)
            
        print(f"!!! WAITING FOR VERDICT: {artifact_path}")
        
        # Ждем появления вердикта (блокирующий вызов для MVP)
        while not os.path.exists(verdict_path):
            time.sleep(2)
            
        with open(verdict_path, "r") as f:
            verdict = json.load(f)
            
        return verdict.get("status") == "approved", verdict.get("comment", "")

    def _execute_command(self, cmd_line):
        """Executes a bash-like command defined in the plan."""
        if cmd_line.startswith("edit:"):
            parts = cmd_line.split(":", 3)
            if len(parts) == 4:
                _, file_path, search, replace = parts
                with open(file_path, "r") as f:
                    content = f.read()
                new_content = content.replace(search, replace)
                with open(file_path, "w") as f:
                    f.write(new_content)
                return True, f"Edited {file_path}"
        elif cmd_line.startswith("bash:"):
            cmd = cmd_line.split(":", 1)[1]
            subprocess.run(cmd, shell=True, check=True)
            return True, f"Executed {cmd}"
        return False, "Unknown command"

    def execute_plan(self, module_name, session_id, user_id, pipeline_engine=None):
        # Fetch Plan
        plan_data = self.artifact_manager.get_latest_artifact(module_name, "plan")
        if not plan_data:
            return False, "Plan not found"
            
        plan_content = plan_data[0]
        log_audit(session_id, user_id, "DEV", f"Executing plan for {module_name}")
        
        # Parse plan
        lines = [line.strip() for line in plan_content.split("\n") if line.strip()]
        
        try:
            for line in lines:
                success, msg = self._execute_command(line)
                if not success:
                    log_audit(session_id, user_id, "DEV_ERROR", f"Action failed: {line}")
            
            # Transition to TEST/POST_SDD
            if pipeline_engine:
                pipeline_engine.transition(PipelineState.POST_SDD)
            log_audit(session_id, user_id, "POST_SDD", "AUTO_TRANSITION_AFTER_DEV")
            return True, "Plan executed and transitioned to POST_SDD"
        except Exception as e:
            return False, str(e)
