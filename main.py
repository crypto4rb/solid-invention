import os
import re
import sys
import json
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

# Terminal colours
RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
BLUE  = "\033[38;5;75m"
GREEN = "\033[38;5;83m"
AMBER = "\033[38;5;220m"
RED   = "\033[38;5;203m"
CYAN  = "\033[38;5;117m"
WHITE = "\033[97m"
GREY  = "\033[38;5;244m"

def c(text, *codes): return "".join(codes) + str(text) + RESET
def info(msg):    print(f"  {c('→', BLUE, BOLD)}  {msg}")
def success(msg): print(f"  {c('✓', GREEN, BOLD)}  {msg}")
def warn(msg):    print(f"  {c('!', AMBER, BOLD)}  {c(msg, AMBER)}")
def error(msg):   print(f"  {c('✗', RED, BOLD)}  {c(msg, RED)}")
def dim(msg):     print(c(f"     {msg}", GREY))
def blank():      print()


def header():
    print()
    print(c("  ╔════════════════════════════════════════╗", BLUE))
    print(c("  ║  ", BLUE) + c("AI ARCHITECT", WHITE + BOLD) + c("                          ║", BLUE))
    print(c("  ║  ", BLUE) + c("Blueprint generator · CrewAI · Modal  ", GREY) + c("║", BLUE))
    print(c("  ╚════════════════════════════════════════╝", BLUE))
    print()


def divider(label=""):
    width = 45
    if label:
        pad  = (width - len(label) - 2) // 2
        line = c("─" * pad + f" {label} " + "─" * (width - pad - len(label) - 2), BLUE, DIM)
    else:
        line = c("─" * width, BLUE, DIM)
    print(f"  {line}")


def agent_step(name: str, description: str, index: int, total: int):
    blank()
    divider(f"{index}/{total}")
    print(f"  {c('◆', BLUE, BOLD)}  {c(name, WHITE, BOLD)}")
    dim(description)


def agent_done(name: str):
    print(f"  {c('◆', GREEN, BOLD)}  {c(name, GREEN)} {c('complete', GREY)}")


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:40].strip("-")


# Clarifier Q&A

def ask_questions(questions: list) -> dict:
    answers = {}
    blank()
    divider("clarification")
    print(f"  {c('◇', AMBER, BOLD)}  {c('A few quick questions before I start', WHITE)}")
    blank()

    for i, q in enumerate(questions):
        label   = q.get("label", f"Question {i+1}")
        text    = q.get("question", "")
        hint    = q.get("hint", "")
        options = q.get("options", [])
        qid     = q.get("id", f"q{i+1}")

        print(f"  {c(f'Q{i+1}', CYAN, BOLD)}  {c(text, WHITE)}")
        if hint:
            dim(hint)
        blank()

        if options:
            for idx, opt in enumerate(options, 1):
                print(f"      {c(str(idx), BLUE, BOLD)}.  {opt}")
            print(f"      {c('c', BLUE, BOLD)}.  Custom answer")
            blank()

            while True:
                try:
                    raw = input(c("      Enter choice: ", GREY)).strip()
                except (EOFError, KeyboardInterrupt):
                    print(); sys.exit(0)

                if raw.isdigit() and 1 <= int(raw) <= len(options):
                    answers[qid] = options[int(raw) - 1]
                    break
                elif raw.lower() == "c":
                    try:
                        custom = input(c("      Your answer: ", GREY)).strip()
                    except (EOFError, KeyboardInterrupt):
                        print(); sys.exit(0)
                    if custom:
                        answers[qid] = custom
                        break
                    else:
                        warn("Please enter an answer.")
                else:
                    warn(f"Enter a number 1-{len(options)} or 'c'.")
        else:
            try:
                ans = input(c("      Your answer: ", GREY)).strip()
            except (EOFError, KeyboardInterrupt):
                print(); sys.exit(0)
            answers[qid] = ans or "(no answer)"

        success(f"Noted: {c(answers[qid], WHITE)}")
        blank()

    return answers


# Diagram cleaner

def clean_diagrams(raw: str) -> str:
    if not raw:
        return raw

    outer = re.match(r"^```(?:markdown)?\s*\n([\s\S]*?)\n```\s*$", raw.strip())
    if outer:
        raw = outer.group(1)
    raw = re.sub(r"^```markdown\s*\n", "", raw.strip())
    raw = re.sub(r"\n```\s*$", "", raw.strip())

    def sanitize_block(code: str) -> str:
        code = code.replace("\r\n", "\n").replace("\r", "\n").strip()
        # Remove semicolons after graph direction
        code = re.sub(r"(graph (?:TD|LR|TB|RL));", r"\1", code)
        # Fix participant A[Label] → participant A as Label
        code = re.sub(r"participant (\w+)\[(.+?)\]", r"participant \1 as \2", code)
        # Fix -->|label|> → -->|label|
        code = re.sub(r"([-.=]{1,2}>?)\s*\|\s*([^|\n]+?)\s*\|\s*>", r"\1|\2|", code)
        code = re.sub(r"(-->|==>|-.->)\s*\|\s*([^|\n]+?)\s*\|\s*>", r"\1|\2|", code)
        # Trim whitespace inside node labels
        code = re.sub(r"\[\s*([^\]\n]+?)\s*\]", lambda m: f"[{m.group(1).strip()}]", code)
        # Fix erDiagram field types
        if "erDiagram" in code:
            type_map = {
                "UUID":      "string",
                "Integer":   "int",
                "Boolean":   "boolean",
                "Enum":      "string",
                "Text":      "string",
                "Timestamp": "datetime",
            }
            code = re.sub(
                r"\b(UUID|Integer|Boolean|Enum|Text|Timestamp)\b",
                lambda m: type_map.get(m.group(1), m.group(1)),
                code,
            )
        return code

    if "```mermaid" in raw:
        blocks = []
        for m in re.finditer(r"```mermaid\s*\n?([\s\S]*?)(?=\n```|\Z)", raw, re.IGNORECASE):
            code = m.group(1).strip()
            if code:
                blocks.append("```mermaid\n" + sanitize_block(code) + "\n```")
        return "\n\n".join(blocks)

    # Fallback: raw %% comment-separated blocks
    parts = re.split(r"(?m)^(%% .+)$", raw)
    output = []
    i = 1
    while i < len(parts) - 1:
        comment = parts[i].strip()
        code    = parts[i + 1].strip()
        if code:
            output.append(f"```mermaid\n{comment}\n{sanitize_block(code)}\n```")
        i += 2

    return "\n\n".join(output)


# HTML assembly

def assemble_html(
    task_id: str,
    product_idea: str,
    outputs: dict,
    template_path: str,
    out_path: str,
):
    with open(template_path, encoding="utf-8") as f:
        html = f.read()

    diagrams_content = clean_diagrams(outputs.get("diagrams", ""))

    content = {
        "requirements":  outputs.get("requirements", ""),
        "backend":       outputs.get("backend", ""),
        "frontend":      outputs.get("frontend", ""),
        "system":        outputs.get("system", ""),
        "data_model":    outputs.get("data_model", ""),
        "cost_estimate": outputs.get("cost_estimate", ""),
        "roadmap":       outputs.get("roadmap", ""),
        "diagrams":      diagrams_content,
    }

    diagrams_len = str(len(re.findall(r"```mermaid", diagrams_content)))
    model_full   = os.getenv("MODEL", "unknown")
    model_name   = model_full.split("/")[-1]
    provider     = os.getenv("PROVIDER", "Local")

    title        = product_idea[:60] + ("…" if len(product_idea) > 60 else "")
    generated_at = datetime.now().strftime("%d %b %Y, %H:%M")

    replacements = {
        "{{TASK_ID}}":       task_id,
        "{{PRODUCT_TITLE}}": title,
        "{{PRODUCT_IDEA}}":  product_idea,
        "{{GENERATED_AT}}":  generated_at,
        "{{DIAGRAMS_LEN}}":  diagrams_len,
        "{{AGENTS_LEN}}":    str(len(AGENT_STEPS)),
        "{{PROVIDER}}":      provider,
        "{{MODEL_NAME}}":    model_name,
        "{{CONTENT_JSON}}":  json.dumps(content, ensure_ascii=False),
    }

    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


# Agent pipeline steps (single source of truth)

AGENT_STEPS = [
    ("Requirements Analyst",  "Analysing product idea and defining requirements"),
    ("Backend Architect",     "Designing backend framework, APIs, and database"),
    ("Frontend Architect",    "Designing frontend stack, state, and routing"),
    ("System Designer",       "Designing infrastructure, deployment, and observability"),
    ("Data Modeller",         "Designing entities, relationships, and schema"),
    ("Cost Estimator",        "Estimating infrastructure costs, team size, and timeline"),
    ("Roadmap Planner",       "Planning MVP scope, sprints, and post-MVP phases"),
    ("Diagram Generator",     "Generating Mermaid diagrams for all architecture views"),
]


# Main

def main():
    header()

    print(f"  {c('What are you building?', WHITE, BOLD)}")
    dim("Describe your product idea in plain English. Be as detailed or brief as you like.")
    blank()

    try:
        idea = input(c("  › ", BLUE, BOLD)).strip()
    except (EOFError, KeyboardInterrupt):
        print(); sys.exit(0)

    if not idea:
        error("No idea entered. Exiting.")
        sys.exit(1)

    blank()

    # Create task ID + output dir
    task_id    = slugify(idea[:30]) + "-" + uuid.uuid4().hex[:6]
    output_dir = Path("outputs") / task_id
    output_dir.mkdir(parents=True, exist_ok=True)

    info(f"Task ID: {c(task_id, CYAN)}")
    info(f"Output:  {c(str(output_dir), CYAN)}")
    blank()

    (output_dir / "idea.txt").write_text(idea)

    from ai_architect.crew import ClarifierCrew, AiArchitect

    # Clarifier
    divider("clarifier")
    print(f"  {c('◆', BLUE, BOLD)}  {c('Clarifier Agent', WHITE, BOLD)}")
    dim("Analysing your idea for ambiguities...")

    try:
        decision = ClarifierCrew().run(idea)
    except Exception as e:
        error(f"Clarifier failed: {e}")
        decision_cls = type("D", (), {"needs_clarification": False, "questions": []})()
        decision = decision_cls

    answers = {}
    if decision.needs_clarification and decision.questions:
        answers = ask_questions([q.model_dump() for q in decision.questions])
        with open(output_dir / "clarification.json", "w") as f:
            json.dump(
                {"questions": [q.model_dump() for q in decision.questions], "answers": answers},
                f, indent=2,
            )
        success("Clarification complete")
    else:
        success("No clarification needed — idea is clear enough")

    # Build clarification context string
    if answers and decision.questions:
        lines = []
        for q in decision.questions:
            ans = answers.get(q.id, "Not answered")
            lines.append(f"Q: {q.question}\nA: {ans}")
        clarification_context = "\n\n".join(lines)
    else:
        clarification_context = "No clarification was needed — proceed with the idea as stated."

    # Agent pipeline
    blank()
    divider("generating")
    blank()

    # Print all steps upfront
    for i, (name, desc) in enumerate(AGENT_STEPS, 1):
        print(f"  {c(str(i), GREY)}  {c(name, GREY)}  {c('·', GREY)}  {c(desc, GREY, DIM)}")

    blank()
    info(f"Starting pipeline — {len(AGENT_STEPS)} agents · this takes a few minutes")
    blank()

    import threading
    import time

    results      = {"outputs": None, "error": None}

    def _run_crew():
        try:
            results["outputs"] = AiArchitect().run(
                product_idea=idea,
                clarification_context=clarification_context,
                output_dir=str(output_dir),
            )
        except Exception as e:
            results["error"] = e

    # t = threading.Thread(target=_run_crew, daemon=True)
    # t.start()

    _run_crew()

    # # Approximate per-agent timing (seconds from start)
    # step_times    = [0, 35, 70, 110, 150, 190, 230, 270]
    # start         = time.time()
    # printed_steps = set()
    # spin          = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    # spin_i        = 0

    # while t.is_alive():
    #     elapsed = time.time() - start
    #     for i, threshold in enumerate(step_times):
    #         if elapsed >= threshold and i not in printed_steps:
    #             name, desc = AGENT_STEPS[i]
    #             agent_step(name, desc, i + 1, len(AGENT_STEPS))
    #             printed_steps.add(i)

    #     sys.stdout.write(f"\r  {c(spin[spin_i % len(spin)], BLUE)}  {c('working...', GREY)}")
    #     sys.stdout.flush()
    #     spin_i += 1
    #     time.sleep(0.12)

    # # Print any steps not yet shown
    # for i in range(len(AGENT_STEPS)):
    #     if i not in printed_steps:
    #         name, desc = AGENT_STEPS[i]
    #         agent_step(name, desc, i + 1, len(AGENT_STEPS))

    # sys.stdout.write("\r" + " " * 40 + "\r")
    # sys.stdout.flush()
    # t.join()

    if results["error"]:
        blank()
        error(f"Pipeline failed: {results['error']}")
        sys.exit(1)

    outputs = results["outputs"]

    blank()
    for name, _ in AGENT_STEPS:
        agent_done(name)

    # HTML report
    blank()
    divider("assembling")
    info("Building HTML report...")

    candidate_paths = [
        Path(__file__).parent / "src" / "ai_architect" / "report_template.html",
        Path(__file__).parent / "report_template.html",
        Path("src/ai_architect/report_template.html"),
        Path("report_template.html"),
    ]
    template_path = next((p for p in candidate_paths if p.exists()), candidate_paths[0])
    report_path   = output_dir / "report.html"

    try:
        assemble_html(
            task_id=task_id,
            product_idea=idea,
            outputs=outputs,
            template_path=str(template_path),
            out_path=str(report_path),
        )
        success(f"Report assembled → {c(str(report_path), CYAN)}")
    except Exception as e:
        error(f"HTML assembly failed: {e}")
        warn("Markdown files are still available in the output directory")

    # Done
    blank()
    divider("done")
    blank()
    print(f"  {c('✓', GREEN, BOLD)}  {c('Architecture blueprint ready', WHITE, BOLD)}")
    blank()
    print(f"  {c('Report :', GREY)}  {c(str(report_path.resolve()), CYAN, BOLD)}")
    print(f"  {c('Files  :', GREY)}  {c(str(output_dir.resolve()), CYAN)}")
    blank()

    try:
        webbrowser.open(report_path.resolve().as_uri())
        dim("Opening in browser...")
    except Exception:
        dim(f"Open manually: file://{report_path.resolve()}")

    blank()


if __name__ == "__main__":
    main()
231355
