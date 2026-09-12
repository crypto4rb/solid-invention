import os
import re
import json
import logging

from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from ai_architect.models import ClarifyDecision, ClarifyQuestion
from langfuse import get_client
from openinference.instrumentation.crewai import CrewAIInstrumentor
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

langfuse = get_client()
# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")

CrewAIInstrumentor().instrument(skip_dep_check=True)

custom_llm = LLM(
    model=os.getenv("MODEL"),
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("API_BASE"),
    temperature=0.3,
    stream=True,
    max_retries=3,
    timeout=600,
)


def extract_json(raw: str) -> dict | None:
    text = re.sub(r"```(?:json)?\s*", "", raw.strip())
    text = re.sub(r"```", "", text)
    start = next((i for i, c in enumerate(text) if c == "{"), None)
    if start is None:
        return None
    depth = end = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        if depth == 0:
            end = i
            break
    json_str = re.sub(r",\s*([}\]])", r"\1", text[start : end + 1])
    try:
        return json.loads(json_str)
    except Exception:
        try:
            return json.loads(json_str.replace("'", '"'))
        except Exception:
            return None


def parse_clarify_decision(raw: str) -> ClarifyDecision:
    data = extract_json(raw)
    if not data:
        return ClarifyDecision(needs_clarification=False, questions=[])
    questions = []
    for q in data.get("questions", []):
        if not isinstance(q, dict):
            continue
        try:
            questions.append(
                ClarifyQuestion(
                    id=q.get("id", f"q{len(questions)+1}"),
                    label=q.get("label", q.get("id", "Question")),
                    question=q.get("question", ""),
                    hint=q.get("hint", ""),
                    options=q.get("options", []),
                    allow_custom=q.get("allow_custom", True),
                )
            )
        except Exception as e:
            logger.warning("Skipping malformed question: %s", e)
    return ClarifyDecision(
        needs_clarification=data.get("needs_clarification", False),
        questions=questions,
    )


def clean_output(val: str) -> str:
    if not val:
        return val
    # Remove "Thought: ..." lines at the top
    val = re.sub(r"^(Thought:[^\n]*\n+)+", "", val.strip())
    # Remove "Final Answer:" prefix
    val = re.sub(r"^Final Answer:\s*\n?", "", val.strip())
    # Remove leading --- dividers
    val = re.sub(r"^-{3,}\s*\n", "", val.strip())
    # Strip outer ```markdown fence
    outer = re.match(r"^```(?:markdown)?\s*\n([\s\S]*?)\n```\s*$", val.strip())
    if outer:
        val = outer.group(1)
    return val.strip()


@CrewBase
class ClarifierCrew:
    agents: list[BaseAgent]
    tasks: list[Task]
    agents_config = "config/clarifier_agents.yaml"
    tasks_config = "config/clarifier_tasks.yaml"

    @agent
    def clarifier(self) -> Agent:
        return Agent(
            config=self.agents_config["clarifier"],  # type: ignore[index]
            verbose=False,
            llm=custom_llm,
            max_iter=3,
            max_retry_limit=3,
        )

    @task
    def clarify_idea(self) -> Task:
        return Task(
            config=self.tasks_config["clarify_idea"],  # type: ignore[index]
            output_pydantic=ClarifyDecision,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )

    def run(self, product_idea: str) -> ClarifyDecision:
        with langfuse.start_as_current_observation(as_type="span", name="clarifier-trace"):
            # result = crew.kickoff()
            # print(result)
            result = self.crew().kickoff(inputs={"product_idea": product_idea})
        
        langfuse.flush()

        if hasattr(result, "pydantic") and result.pydantic:
            return result.pydantic
        raw = getattr(result, "raw", None) or str(result)
        return parse_clarify_decision(raw)


@CrewBase
class AiArchitect:
    agents: list[BaseAgent]
    tasks: list[Task]
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def requirements_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["requirements_analyst"],  # type: ignore[index]
            verbose=True,
            llm=custom_llm,
            max_iter=3,
            max_retry_limit=3,
        )

    @agent
    def backend_architect(self) -> Agent:
        return Agent(
            config=self.agents_config["backend_architect"],  # type: ignore[index]
            verbose=True,
            llm=custom_llm,
            max_iter=3,
            max_retry_limit=3,
        )

    @agent
    def frontend_architect(self) -> Agent:
        return Agent(
            config=self.agents_config["frontend_architect"],  # type: ignore[index]
            verbose=True,
            llm=custom_llm,
            max_iter=3,
            max_retry_limit=3,
        )

    @agent
    def system_designer(self) -> Agent:
        return Agent(
            config=self.agents_config["system_designer"],  # type: ignore[index]
            verbose=True,
            llm=custom_llm,
            max_iter=3,
            max_retry_limit=3,
        )

    @agent
    def data_modeller(self) -> Agent:
        return Agent(
            config=self.agents_config["data_modeller"],  # type: ignore[index]
            verbose=True,
            llm=custom_llm,
            max_iter=3,
            max_retry_limit=3,
        )

    @agent
    def cost_estimator(self) -> Agent:
        return Agent(
            config=self.agents_config["cost_estimator"],  # type: ignore[index]
            verbose=True,
            llm=custom_llm,
            max_iter=3,
            max_retry_limit=3,
        )

    @agent
    def roadmap_planner(self) -> Agent:
        return Agent(
            config=self.agents_config["roadmap_planner"],  # type: ignore[index]
            verbose=True,
            llm=custom_llm,
            max_iter=3,
            max_retry_limit=3,
        )

    @agent
    def diagram_generator(self) -> Agent:
        from pathlib import Path
        SKILLS_DIR = str(
            Path(__file__)
            .parent
            .resolve()
            / "skills"
            / "mermaid-diagrams"
        )
        return Agent(
            config=self.agents_config["diagram_generator"],  # type: ignore[index]
            verbose=True,
            llm=custom_llm,
            max_iter=3,
            max_retry_limit=3,
            skills=[SKILLS_DIR],
        )

    @task
    def analyze_requirements(self) -> Task:
        return Task(config=self.tasks_config["analyze_requirements"])  # type: ignore[index]

    @task
    def design_backend(self) -> Task:
        return Task(config=self.tasks_config["design_backend"])  # type: ignore[index]

    @task
    def design_frontend(self) -> Task:
        return Task(config=self.tasks_config["design_frontend"])  # type: ignore[index]

    @task
    def design_system(self) -> Task:
        return Task(config=self.tasks_config["design_system"])  # type: ignore[index]

    @task
    def design_data_model(self) -> Task:
        return Task(config=self.tasks_config["design_data_model"])  # type: ignore[index]

    @task
    def estimate_costs(self) -> Task:
        return Task(config=self.tasks_config["estimate_costs"])  # type: ignore[index]

    @task
    def plan_roadmap(self) -> Task:
        return Task(config=self.tasks_config["plan_roadmap"])  # type: ignore[index]

    @task
    def generate_diagrams(self) -> Task:
        return Task(config=self.tasks_config["generate_diagrams"])  # type: ignore[index]

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )

    def run(self, product_idea: str, clarification_context: str, output_dir: str) -> dict:
        inputs = {
            "product_idea": product_idea,
            "clarification_context": clarification_context,
            "output_dir": output_dir,
        }
        
        crew_obj = self.crew()
        with langfuse.start_as_current_observation(as_type="span", name="architecture-run"):
        
            crew_obj.kickoff(inputs=inputs)
        
        langfuse.flush()

        # crew_obj.kickoff(inputs=inputs)

        for task_obj in crew_obj.tasks:
            logger.info(
                "TASK=%s ROLE=%s OUTPUT=%s",
                getattr(task_obj, "name", None),
                getattr(task_obj.agent, "role", None),
                bool(task_obj.output),
            )
        
        langfuse.flush()

        # Map task name keywords → output dict keys
        task_map = {
            "analyze_requirements": "requirements",
            "design_backend":       "backend",
            "design_frontend":      "frontend",
            "design_system":        "system",
            "design_data_model":    "data_model",
            "estimate_costs":       "cost_estimate",
            "plan_roadmap":         "roadmap",
            "generate_diagrams":    "diagrams",
        }

        # Fallback: match by agent role keyword
        role_map = [
            ("requirement",  "requirements"),
            ("backend",      "backend"),
            ("frontend",     "frontend"),
            ("system",       "system"),
            ("data",         "data_model"),
            ("cost",         "cost_estimate"),
            ("roadmap",      "roadmap"),
            ("diagram",      "diagrams"),
        ]

        outputs = {}

        for task_obj in crew_obj.tasks:
            task_name  = getattr(task_obj, "name", "") or ""
            agent_role = str(getattr(task_obj.agent, "role", "")).lower()

            if not (hasattr(task_obj, "output") and task_obj.output):
                continue
            raw = getattr(task_obj.output, "raw", None) or str(task_obj.output)

            matched = False
            for task_key, output_key in task_map.items():
                if task_key in task_name.lower():
                    outputs[output_key] = raw
                    matched = True
                    break

            if not matched:
                for keyword, output_key in role_map:
                    if keyword in agent_role and output_key not in outputs:
                        outputs[output_key] = raw
                        break

        # Fallback: read from output files written directly by tasks
        file_map = {
            "requirements": os.path.join(output_dir, "requirements.md"),
            "backend":      os.path.join(output_dir, "backend_architecture.md"),
            "frontend":     os.path.join(output_dir, "frontend_architecture.md"),
            "system":       os.path.join(output_dir, "system_design.md"),
            "data_model":   os.path.join(output_dir, "data_model.md"),
            "cost_estimate":os.path.join(output_dir, "cost_estimate.md"),
            "roadmap":      os.path.join(output_dir, "roadmap.md"),
            "diagrams":     os.path.join(output_dir, "diagrams.md"),
        }
        for key, path in file_map.items():
            if key not in outputs and os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    outputs[key] = f.read()

        for key in list(outputs.keys()):
            outputs[key] = clean_output(outputs[key])

        return outputs
    
