import os
import re
import time
import zipfile
from pathlib import Path

from agent_framework import Agent

from backend.agents.requirement_analysis_agent import RequirementAnalysisAgent
from backend.agents.user_story_agent import UserStoryAgent
from backend.agents.architecture_agent import ArchitectureAgent
from backend.agents.coding_agent import CodingAgent
from backend.agents.code_review_agent import CodeReviewAgent
from backend.agents.testing_agent import TestingAgent
from backend.agents.documentation_agent import DocumentationAgent
from backend.agents.deployment_agent import DeploymentAgent
from backend.agents.chat_agent import ChatAgent
from backend.service.service import OpenAIService


class SDLCOrchestrator:

    def __init__(self):
        if os.environ.get("VERCEL"):
            self.output_root = Path("/tmp/output")
        else:
            self.output_root = Path("output")
        self.output_root.mkdir(parents=True, exist_ok=True)

    # ---------------- INTENT CLASSIFICATION ----------------
    def _is_sdlc_request_fallback(self, message: str) -> bool:
        """Keyword heuristic used only if the classifier call below fails
        (e.g. the model deployment is briefly unreachable) -- deliberately
        crude, since it exists purely as a safety net, not the real decision."""
        text = (message or "").lower().strip()
        project_verbs = [
            "create", "build", "develop", "generate", "design", "implement",
            "make", "construct", "architect", "engineer", "scaffold", "code", "program"
        ]
        project_nouns = [
            "system", "application", "app", "project", "platform", "api",
            "website", "web app", "webapp", "service", "tool", "portal",
            "dashboard", "backend", "frontend", "software", "crud"
        ]
        has_verb = any(v in text for v in project_verbs)
        has_noun = any(n in text for n in project_nouns)
        return has_verb and has_noun

    async def is_sdlc_request(self, message: str) -> bool:
        """
        Decide whether this message is asking for a full SDLC project build
        (requirements/architecture/code/tests/docs/deployment) versus a normal
        chat question. A fixed verb+noun keyword match is too brittle -- real
        requests are phrased in far too many ways for a keyword list to catch
        ("I need a tool that tracks hostel residents", "set up a REST API for
        orders", etc.), so an LLM call decides instead, the same way title
        generation and chat intent already do elsewhere in this app.
        """
        text = (message or "").lower().strip()

        # Fast, unambiguous shortcut -- skip the round-trip when the user says
        # so explicitly.
        if any(t in text for t in ["sdlc", "pipeline", "only code", "documentation only", "requirements +"]):
            return True

        try:
            classifier = Agent(
                client=OpenAIService(),
                instructions="""
You classify a user's chat message for a developer assistant that can either (a) hold
a normal conversation, or (b) run a full SDLC pipeline that generates requirements,
architecture, code, tests, documentation, and deployment instructions for a software
project.

Classify as SDLC if the user is asking to build, create, generate, scaffold, or
develop an application, system, API, website, tool, script, or any other software
artifact -- regardless of exact phrasing.

Classify as CHAT for everything else: questions, explanations, comparisons, casual
conversation, or requests to just talk about code/architecture without generating a
project.

Reply with EXACTLY one word, nothing else: SDLC or CHAT.
""",
            )
            result = await classifier.run(f"Message: {message}")
            verdict = (result.text if hasattr(result, "text") else str(result)).strip().upper()
            return verdict.startswith("SDLC")
        except Exception as e:
            print(f"[orchestrator] intent classifier failed, falling back to heuristic: {e}")
            return self._is_sdlc_request_fallback(message)

    # ---------------- CLEAN TASK NAME ----------------
    def clean_task_name(self, name: str) -> str:
        name = name.strip()
        name = re.sub(r'^(create a|build a|develop a)\s+', '', name, flags=re.IGNORECASE)
        name = name[:50].strip()
        return (
            name.strip()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
        ) or "project"

    # ---------------- SAVE FILE ----------------
    def save_output(self, folder, filename, content):
        filepath = os.path.join(folder, filename)
        os.makedirs(folder, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as file:
            if hasattr(content, "text"):
                text = content.text
            else:
                text = str(content)
            # Remove markdown code fences if the agent wraps the whole output
            text = text.strip()
            fenced = re.search(r"^```(?:[^\n]*)\n([\s\S]*?)```$", text)
            if fenced:
                text = fenced.group(1).strip()
            file.write(text)

    # ---------------- LOGGING ----------------
    def log_start(self, name):
        print(f"\n🔄 {name} → Processing...")

    def log_done(self, name):
        print(f"✅ {name} → Completed")

    # ---------------- SANITISE AGENT-PROVIDED FILENAME ----------------
    def sanitise_filename(self, raw: str, fallback: str = "code.py") -> str:
        """
        Clean the filename the agent emits so it is safe to use on disk.
        """
        name = raw.strip().strip('"').strip("'")
        name = os.path.basename(name)
        name = re.sub(r'[^\w.\-]', '_', name)
        name = re.sub(r'_+', '_', name).strip('_')
        return name if name else fallback

    # ---------------- CHAT EXECUTION ----------------
    async def handle_chat(self, message: str, history: str = "", context: str = "") -> str:
        """Handle a normal chat message using ChatAgent."""
        self.log_start("ChatAgent")
        agent = ChatAgent()
        context_block = (
            f"Reference Context (from the internal knowledge base — use this information "
            f"to answer accurately, but do not mention filenames or say \"according to the "
            f"knowledge base\"; just answer naturally):\n{context}\n\n"
            if context else ""
        )
        prompt = message
        if history or context_block:
            prompt = f"{history}{context_block}Current User Request: {message}"
        result = await agent.run(prompt)
        reply = result.text if hasattr(result, "text") else str(result)
        self.log_done("ChatAgent")
        return reply

    # ---------------- SDLC EXECUTION ----------------
    async def execute_sdlc(self, user_request: str, history: str = "", context: str = "") -> dict:
        
        task_name = self.clean_task_name(user_request)
        folder = os.path.join(self.output_root, task_name)
        os.makedirs(folder, exist_ok=True)

        print("\n" + "=" * 60)
        print("🚀 AI MULTI-AGENT SDLC FRAMEWORK STARTED (AGENT-DRIVEN)")
        print("=" * 60)

        orchestrator = Agent(
            client=OpenAIService(),
            instructions="""
You are the SDLC Orchestrator Agent. Your job is to help users build software by coordinating specialist agents.

You have access to these tools (specialist agents):

- requirement_analysis(user_request: str) -> str
  Use this to generate clear, structured requirements from a user request.

- user_story_generation(requirements: str) -> str
  Use this to turn requirements into user stories.

- architecture_design(user_stories: str) -> str
  Use this to create a system architecture based on user stories.

- code_generation(architecture: str, language: str) -> str
  Use this to generate COMPLETE, PRODUCTION-READY code in the specified language.
  Do NOT output placeholders, examples, or "..." — generate full working code.

- code_review(code: str) -> str
  Use this to generate a comprehensive code review covering both quality and performance.

- testing(code: str) -> str
  Use this to generate a comprehensive testing report covering unit, integration, and security testing.

- documentation(architecture: str, project_name: str) -> str
  Use this to generate FULL documentation based on the architecture and project name.

- deployment(architecture: str, code: str, project_name: str) -> str
  Use this to generate deployment plans and instructions based on the project name.

Rules:

0. REFERENCE CONTEXT (IF PROVIDED)
   - If a "Reference Context" section appears in the prompt, treat it as authoritative
     supporting material and incorporate relevant facts into REQUIREMENTS/ARCHITECTURE/
     DOCUMENTATION as appropriate. Do not mention filenames or say "according to the
     knowledge base" anywhere in the output — just use the facts naturally.
   - If no such section is present, proceed exactly as you do today.

1. UNDERSTAND THE USER REQUEST (SELECTIVE EXECUTION)
   - CRITICAL: If the user asks for ONLY documentation (e.g., "Generate only documentation"), YOU MUST ONLY output [DOCUMENTATION] and [FILENAME]. DO NOT call code_generation, do not output [CODE], do not output [TESTING], etc.
   - CRITICAL: If the user asks for ONLY code, call only code_generation and output ONLY [CODE] and [FILENAME].
   - CRITICAL: If the user asks for ONLY tests, call only the testing tool and output ONLY the test sections.
   - If the user asks for a complete project, run the full pipeline.

2. DO NOT RUN ALL TOOLS BY DEFAULT
   - Only call the tools that match what the user asked for. If the prompt says "only", ignore all other steps.

3. ALWAYS GENERATE COMPLETE CONTENT IN MARKDOWN (NEVER RAW JSON)
   - Do NOT output raw JSON objects. Use properly formatted Markdown.
   - For code: complete files, no placeholders.
   - For tests: full test functions with assertions.
   - For docs: full markdown sections, not outlines.
   - CRITICAL: Do NOT generate an "Agent Execution Log", execution times, or any progress logs. DO NOT list out which agents you called. Do NOT generate a generic "Project Report", summary, or any other unrequested file. Only use the tools provided and output their exact sections.

4. DECIDE THE FILENAME
   - Read the user request and decide the most appropriate filename WITH extension.
   - Use the actual purpose of the code, not a generic name.
   - Always emit this filename in a [FILENAME] section.

5. OUTPUT FORMAT (VERY IMPORTANT)
   Return your final answer as a single plain text document with clearly marked sections.
   Use this exact format:

   [FILENAME]
   main.py
   [/FILENAME]

   [REQUIREMENTS]
   ...requirements text...
   [/REQUIREMENTS]

   [USER_STORIES]
   ...user stories text...
   [/USER_STORIES]

   [ARCHITECTURE]
   ...architecture text...
   [/ARCHITECTURE]

   [CODE]
   ...source code...
   [/CODE]

   [CODE_REVIEW]
   ...code review text...
   [/CODE_REVIEW]

   [TESTING]
   ...testing text...
   [/TESTING]

   [DOCUMENTATION]
   ...documentation text...
   [/DOCUMENTATION]

   [DEPLOYMENT]
   ...deployment text...
   [/DEPLOYMENT]

   RULES:
   - [FILENAME] must ALWAYS be present — even if only code is generated.
   - [FILENAME] must be a real filename with the correct extension, e.g. main.py not python.
   - Only include sections that were actually generated.
   - Do NOT wrap output in JSON. Use plain text with section markers only.
""",
            tools=[
                RequirementAnalysisAgent,
                UserStoryAgent,
                ArchitectureAgent,
                CodingAgent,
                CodeReviewAgent,
                TestingAgent,
                DocumentationAgent,
                DeploymentAgent,
            ],
        )

        context_block = (
            f"\nReference Context (from internal knowledge base — incorporate naturally, "
            f"do not mention filenames or the knowledge base):\n{context}\n" if context else ""
        )

        prompt = f"""
Task: {task_name}
{history}{context_block}
Current User Request: {user_request}
"""

        self.log_start("Orchestrator Agent (Master LLM)")
        start_time = time.time()
        
        try:
            result = await orchestrator.run(prompt)
            text = result.text if hasattr(result, "text") else str(result)
        except Exception as e:
            print(f"❌ Orchestrator Agent Failed: {e}")
            return {
                "mode": "sdlc",
                "project_title": task_name,
                "project_folder": task_name,
                "reply": f"An error occurred during orchestration: {e}",
                "files": {},
                "has_zip": False,
                "error": str(e)
            }
            
        self.log_done("Orchestrator Agent (Master LLM)")

        # ----------------- Parse sections -----------------
        sections = {}

        def extract_section(start_tag, end_tag):
            start = text.find(start_tag)
            if start == -1:
                return None
            start += len(start_tag)
            end = text.find(end_tag, start)
            if end == -1:
                return None
            return text[start:end].strip()

        sections["requirements"]  = extract_section("[REQUIREMENTS]",  "[/REQUIREMENTS]")
        sections["user_stories"]  = extract_section("[USER_STORIES]",  "[/USER_STORIES]")
        sections["architecture"]  = extract_section("[ARCHITECTURE]",  "[/ARCHITECTURE]")
        sections["code"]          = extract_section("[CODE]",          "[/CODE]")
        sections["code_review"]   = extract_section("[CODE_REVIEW]",   "[/CODE_REVIEW]")
        sections["testing"]       = extract_section("[TESTING]",       "[/TESTING]")
        sections["documentation"] = extract_section("[DOCUMENTATION]", "[/DOCUMENTATION]")
        sections["deployment"]    = extract_section("[DEPLOYMENT]",    "[/DEPLOYMENT]")

        # ── Agent-decided filename ────────────────────────────────────────────
        raw_filename  = extract_section("[FILENAME]", "[/FILENAME]") or "code.py"
        code_filename = self.sanitise_filename(raw_filename)
        
        print(f"\n📄 Agent-decided filename: {code_filename}")

        files_payload = {}

        # ----------------- Save files & build payload -----------------
        if sections["requirements"]:
            self.save_output(folder, "Requirements.md", sections["requirements"])
            print(f"💾 Saved: Requirements.md")
            files_payload["requirements"] = {
                "title": "Requirements",
                "content": sections["requirements"],
                "file_name": "Requirements.md",
                "is_code": False
            }

        if sections["user_stories"]:
            self.save_output(folder, "User_Stories.md", sections["user_stories"])
            print(f"💾 Saved: User_Stories.md")
            files_payload["user_stories"] = {
                "title": "User Stories",
                "content": sections["user_stories"],
                "file_name": "User_Stories.md",
                "is_code": False
            }

        if sections["architecture"]:
            self.save_output(folder, "Architecture.md", sections["architecture"])
            print(f"💾 Saved: Architecture.md")
            files_payload["architecture"] = {
                "title": "Architecture",
                "content": sections["architecture"],
                "file_name": "Architecture.md",
                "is_code": False
            }

        if sections["code"]:
            self.save_output(folder, code_filename, sections["code"])
            print(f"💾 Saved: {code_filename}")
            files_payload["code"] = {
                "title": "Source Code",
                "content": sections["code"],
                "file_name": code_filename,
                "is_code": True
            }

        if sections["code_review"]:
            self.save_output(folder, "Code_Review.md", sections["code_review"])
            print("💾 Saved: Code_Review.md")
            files_payload["code_review"] = {
                "title": "Code Review",
                "content": sections["code_review"],
                "file_name": "Code_Review.md",
                "is_code": False
            }

        if sections["testing"]:
            self.save_output(folder, "Testing_Report.md", sections["testing"])
            print("💾 Saved: Testing_Report.md")
            files_payload["testing_report"] = {
                "title": "Testing Report",
                "content": sections["testing"],
                "file_name": "Testing_Report.md",
                "is_code": False
            }

        if sections["documentation"]:
            self.save_output(folder, "Documentation.md", sections["documentation"])
            print(f"💾 Saved: Documentation.md")
            files_payload["documentation"] = {
                "title": "Documentation",
                "content": sections["documentation"],
                "file_name": "Documentation.md",
                "is_code": False
            }

        if sections["deployment"]:
            self.save_output(folder, "Deployment.md", sections["deployment"])
            print(f"💾 Saved: Deployment.md")
            files_payload["deployment"] = {
                "title": "Deployment",
                "content": sections["deployment"],
                "file_name": "Deployment.md",
                "is_code": False
            }

        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print("🎉 ALL AGENTS COMPLETED SUCCESSFULLY")
        print(f"⏱️ Time taken: {elapsed:.1f}s")
        print(f"📁 OUTPUT SAVED IN: {folder}")
        print("=" * 60)
        
        # Build a single summary report for the UI reply block
        report = ""
        
        # Generate ZIP
        zip_path = os.path.join(folder, "project.zip")
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        if file != "project.zip":
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, folder)
                            zf.write(file_path, arcname)
            has_zip = True
        except Exception as e:
            print(f"Failed to create ZIP: {e}")
            has_zip = False

        return {
            "mode": "sdlc",
            "project_title": task_name,
            "project_folder": task_name,
            "reply": report,
            "files": files_payload,
            "has_zip": has_zip
        }