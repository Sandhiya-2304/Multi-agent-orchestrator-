import os
import re

from agent_framework import Agent

from agents.requirement_analysis_agent import RequirementAnalysisAgent
from agents.user_story_agent import UserStoryAgent
from agents.architecture_agent import ArchitectureAgent
from agents.coding_agent import CodingAgent
from agents.quality_review_agent import QualityReviewAgent
from agents.performance_review_agent import PerformanceReviewAgent
from agents.unit_testing_agent import UnitTestingAgent
from agents.integration_testing_agent import IntegrationTestingAgent
from agents.security_testing_agent import SecurityTestingAgent
from agents.documentation_agent import DocumentationAgent
from agents.deployment_agent import DeploymentAgent
from service.service import OpenAIService


class SDLCOrchestrator:
    def clean_task_name(self, name: str) -> str:
        return (
            name.strip()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
        )

    def save_output(self, folder, filename, content):
        filepath = os.path.join(folder, filename)
        os.makedirs(folder, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as file:
            if hasattr(content, "text"):
                text = content.text
            else:
                text = str(content)
            file.write(text)

    def log_start(self, name):
        print(f"\n🔄 {name} → Processing...")

    def log_done(self, name):
        print(f"✅ {name} → Completed")

    def sanitise_filename(self, raw: str, fallback: str = "code.py") -> str:
        name = raw.strip().strip('"').strip("'")
        name = os.path.basename(name)
        name = re.sub(r"[^\w.\-]", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        return name if name else fallback

    async def execute(self, task_name, user_request):
        print("\n" + "=" * 60)
        print("🚀 AI MULTI-AGENT SDLC FRAMEWORK STARTED (AGENT-DRIVEN)")
        print("=" * 60)

        orchestrator = Agent(
            client=OpenAIService(),
            instructions="""
You are the SDLC Orchestrator Agent. Your job is to help users build software by coordinating specialist agents.

You have access to these tools (specialist agents):
- requirement_analysis(user_request: str) -> str
- user_story_generation(requirements: str) -> str
- architecture_design(user_stories: str) -> str
- code_generation(architecture: str, language: str) -> str
- quality_review(code: str) -> str
- performance_review(code: str) -> str
- unit_testing(code: str) -> str
- integration_testing(code: str) -> str
- security_testing(code: str) -> str
- documentation(architecture: str) -> str
- deployment(architecture: str, code: str, documentation: str) -> str

INTERPRETING THE USER REQUEST (IMPORTANT):
- If the user request mentions building/creating/generating any app/system/platform/website/dashboard/service/project/api/backend/frontend, treat it as a FULL software development request.
- For such requests, use the FULL SDLC pipeline by default:
  1. requirement_analysis
  2. user_story_generation
  3. architecture_design
  4. code_generation
  5. quality_review
  6. performance_review
  7. unit_testing
  8. integration_testing
  9. security_testing
  10. documentation
  11. deployment

  1. UNDERSTAND THE USER REQUEST
   - If the user asks for ONLY code, call only code_generation.
   - If the user asks for ONLY documentation, call only documentation.
   - If the user asks for ONLY tests, call the relevant testing tools.
   - If the user asks for a complete project, run the full pipeline:
     requirement_analysis → user_story_generation → architecture_design → code_generation
     → unit_testing → integration_testing → security_testing → documentation → deployment.

OUTPUT FORMAT:
[PROJECT_NAME]
short_name
[/PROJECT_NAME]

[FILENAME]
main.py
[/FILENAME]

[REQUIREMENTS]
...
[/REQUIREMENTS]

[USER_STORIES]
...
[/USER_STORIES]

[ARCHITECTURE]
...
[/ARCHITECTURE]

[CODE]
...
[/CODE]
[TESTING]
[UNIT_TESTS]
...
[/UNIT_TESTS]

[INTEGRATION_TESTS]
...
[/INTEGRATION_TESTS]

[SECURITY_TESTS]
...
[/SECURITY_TESTS]
[/TESTING]

[CODE_REVIEW]
[QUALITY_REVIEW]
...
[/QUALITY_REVIEW]

[PERFORMANCE_REVIEW]
...
[/PERFORMANCE_REVIEW]
[/CODE_REVIEW]

[DOCUMENTATION]
...
[/DOCUMENTATION]

[DEPLOYMENT]
...
[/DEPLOYMENT]
""",
            tools=[
                RequirementAnalysisAgent,
                UserStoryAgent,
                ArchitectureAgent,
                CodingAgent,
                QualityReviewAgent,
                PerformanceReviewAgent,
                UnitTestingAgent,
                IntegrationTestingAgent,
                SecurityTestingAgent,
                DocumentationAgent,
                DeploymentAgent,
            ],
        )

        prompt = f"""
Task: {task_name}
User request: {user_request}
"""

        self.log_start("Orchestrator Agent")
        result = await orchestrator.run(prompt)
        self.log_done("Orchestrator Agent")

        text = result.text if hasattr(result, "text") else str(result)

        def extract_section(start_tags, end_tags):
            if not isinstance(start_tags, (list, tuple)):
                start_tags = [start_tags]
            if not isinstance(end_tags, (list, tuple)):
                end_tags = [end_tags]

            for start_tag in start_tags:
                start_match = re.search(re.escape(start_tag), text, re.IGNORECASE)
                if not start_match:
                    continue

                start = start_match.end()
                for end_tag in end_tags:
                    end_match = re.search(re.escape(end_tag), text[start:], re.IGNORECASE)
                    if not end_match:
                        continue
                    return text[start:start + end_match.start()].strip()
            return None

        project_name_raw = extract_section("[PROJECT_NAME]", "[/PROJECT_NAME]") or task_name
        project_name_clean = self.sanitise_filename(
            project_name_raw.replace(" ", "_"),
            fallback="my_project"
        )

        folder = os.path.join("output", project_name_clean)
        os.makedirs(folder, exist_ok=True)

        raw_filename = extract_section("[FILENAME]", "[/FILENAME]") or "code.py"
        code_filename = self.sanitise_filename(raw_filename)

        sections = {
            "requirements": extract_section("[REQUIREMENTS]", "[/REQUIREMENTS]"),
            "user_stories": extract_section("[USER_STORIES]", "[/USER_STORIES]"),
            "architecture": extract_section("[ARCHITECTURE]", "[/ARCHITECTURE]"),
            "code": extract_section("[CODE]", "[/CODE]"),
            "code_review": extract_section(["[CODE_REVIEW]", "[CODE REVIEW]"], ["[/CODE_REVIEW]", "[/CODE REVIEW]"]),
            "testing": extract_section("[TESTING]", "[/TESTING]"),
            "documentation": extract_section("[DOCUMENTATION]", "[/DOCUMENTATION]"),
            "deployment": extract_section("[DEPLOYMENT]", "[/DEPLOYMENT]"),
        }

        section_files = {
            "requirements": "requirements.txt",
            "user_stories": "user_stories.txt",
            "architecture": "architecture.txt",
            "code_review": "code_review.txt",
            "testing": "testing.txt",
            "documentation": "documentation.txt",
            "deployment": "deployment.txt",
        }

        for section_name, filename in section_files.items():
            if sections.get(section_name):
                self.save_output(folder, filename, sections[section_name])
                print(f"💾 Saved: {filename}")

        if sections["code"]:
            self.save_output(folder, code_filename, sections["code"])
            print(f"💾 Saved: {code_filename}")

        print("\n" + "=" * 60)
        print("🎉 ALL AGENTS COMPLETED SUCCESSFULLY")
        print("=" * 60)

        sections["filename"] = code_filename
        return sections