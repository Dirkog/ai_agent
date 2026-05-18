"""Multi-agent orchestrator — main AI assigns roles and delegates"""
import json
import re
from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass, field
from enum import Enum


class AgentRole(Enum):
    ARCHITECT = "architect"      # Designs structure, APIs, schemas
    CODER = "coder"              # Writes implementation code
    REVIEWER = "reviewer"        # Code review, quality checks
    TESTER = "tester"            # Writes and runs tests
    DEBUGGER = "debugger"        # Fixes bugs, handles errors
    DEVOPS = "devops"            # Docker, CI/CD, deployment
    SCRUM_MASTER = "scrum"       # Plans tasks, tracks progress


@dataclass
class SubAgent:
    role: AgentRole
    name: str
    system_prompt: str
    model: str = "default"
    tasks_completed: int = 0
    status: str = "idle"  # idle, working, done, error
    output: str = ""


class Orchestrator:
    """Main orchestrator that assigns roles and coordinates sub-agents"""

    ROLE_PROMPTS = {
        AgentRole.ARCHITECT: """You are a Software Architect. Design clean, scalable systems.
Your job: create project structure, define APIs, choose tech stack, write schemas.
Output: architecture docs, file structure, interface definitions.
Do NOT write implementation — only design.""",

        AgentRole.CODER: """You are a Senior Developer. Write clean, production-ready code.
Your job: implement features based on architecture docs. Follow best practices.
Output: source code files with full implementation.
Use tools to read/write files.""",

        AgentRole.REVIEWER: """You are a Code Reviewer. Find bugs, smells, security issues.
Your job: review code against standards. Check for: bugs, performance, security, style.
Output: review report with specific line references and fix suggestions.""",

        AgentRole.TESTER: """You are a QA Engineer. Write comprehensive tests.
Your job: unit tests, integration tests, edge cases. Aim for high coverage.
Output: test files using pytest.""",

        AgentRole.DEBUGGER: """You are a Debugger. Fix errors and optimize.
Your job: analyze error logs, stack traces, fix root causes. Optimize hot paths.
Output: fixed code with explanations of changes.""",

        AgentRole.DEVOPS: """You are a DevOps Engineer. Handle deployment and infra.
Your job: Docker, CI/CD, env configs, monitoring setup.
Output: Dockerfile, docker-compose, GitHub Actions, scripts.""",

        AgentRole.SCRUM_MASTER: """You are a Project Manager. Break down tasks.
Your job: analyze requirements, create task list, estimate complexity, track progress.
Output: task breakdown with acceptance criteria.""",
    }

    def __init__(self, provider_manager=None):
        self.provider_manager = provider_manager
        self.agents: List[SubAgent] = []
        self.task_history: List[Dict] = []
        self.current_plan: List[str] = []

    def analyze_and_assign(self, task: str) -> List[SubAgent]:
        """Main AI analyzes task and assigns roles automatically"""
        # In real implementation, this calls the main LLM to decide roles
        # Here we use heuristic + LLM prompt

        prompt = f"""Analyze this development task and determine which roles are needed.
Available roles: architect, coder, reviewer, tester, debugger, devops, scrum.

Task: {task}

Respond ONLY with a JSON array of role names needed, in execution order.
Example: ["scrum", "architect", "coder", "tester", "reviewer"]
"""
        # Simulate LLM decision (in production, call provider_manager.chat)
        roles_needed = self._heuristic_role_selection(task)

        self.agents = []
        for role in roles_needed:
            agent = SubAgent(
                role=role,
                name=f"{role.value}_agent",
                system_prompt=self.ROLE_PROMPTS[role],
                model="default"
            )
            self.agents.append(agent)

        print(f"[Orchestrator] Assigned {len(self.agents)} agents: {[a.role.value for a in self.agents]}")
        return self.agents

    def _heuristic_role_selection(self, task: str) -> List[AgentRole]:
        """Heuristic role selection based on task keywords"""
        task_lower = task.lower()
        roles = []

        # Always start with planning
        roles.append(AgentRole.SCRUM_MASTER)

        # Architecture needed for new projects
        if any(k in task_lower for k in ["create", "build", "new project", "design", "api", "structure"]):
            roles.append(AgentRole.ARCHITECT)

        # Coding always needed unless pure review
        if not any(k in task_lower for k in ["only review", "just review", "audit"]):
            roles.append(AgentRole.CODER)

        # Testing
        if any(k in task_lower for k in ["test", "coverage", "pytest"]):
            roles.append(AgentRole.TESTER)

        # Review at the end
        if any(k in task_lower for k in ["review", "quality", "clean", "refactor"]):
            roles.append(AgentRole.REVIEWER)

        # Debugging
        if any(k in task_lower for k in ["fix", "bug", "error", "debug", "broken"]):
            roles.append(AgentRole.DEBUGGER)

        # DevOps
        if any(k in task_lower for k in ["docker", "deploy", "ci/cd", "pipeline", "infra"]):
            roles.append(AgentRole.DEVOPS)

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for r in roles:
            if r not in seen:
                seen.add(r)
                unique.append(r)

        return unique

    def run_workflow(self, task: str) -> Generator[str, None, None]:
        """Execute full multi-agent workflow"""
        yield f"[Orchestrator] Analyzing task: {task[:100]}...\n"

        agents = self.analyze_and_assign(task)
        yield f"[Orchestrator] Team assembled: {', '.join(a.name for a in agents)}\n"

        shared_context = f"Original task: {task}\n\n"

        for i, agent in enumerate(agents, 1):
            yield f"\n{'='*60}\n"
            yield f"[Phase {i}/{len(agents)}] {agent.role.value.upper()} — {agent.name}\n"
            yield f"{'='*60}\n"

            agent.status = "working"

            # Build prompt for this agent
            agent_prompt = f"""{agent.system_prompt}

SHARED CONTEXT (from previous phases):
{shared_context[:3000]}

YOUR TASK:
Based on the above context, execute your role-specific responsibilities.
Use tools to interact with the file system.
Output your results clearly.
"""

            # In production: call agent.run(agent_prompt) and stream results
            # Here we simulate
            yield f"[{agent.name}] Working...\n"

            # Simulate work output
            agent.output = f"Completed {agent.role.value} phase"
            agent.status = "done"
            agent.tasks_completed += 1

            shared_context += f"\n\n[{agent.role.value.upper()} OUTPUT]:\n{agent.output}\n"

            yield f"[{agent.name}] ✅ Done\n"

        yield f"\n{'='*60}\n"
        yield "[Orchestrator] All phases complete. Synthesizing final result...\n"
        yield self._synthesize_results()

    def _synthesize_results(self) -> str:
        """Combine all agent outputs into final deliverable"""
        summary = "\n📋 PROJECT DELIVERABLE SUMMARY\n"
        summary += "=" * 60 + "\n"
        for agent in self.agents:
            summary += f"\n[{agent.role.value.upper()}] {agent.status.upper()}\n"
            summary += f"  Tasks: {agent.tasks_completed}\n"
            summary += f"  Output: {agent.output[:200]}...\n"
        summary += "\n" + "=" * 60 + "\n"
        return summary

    def get_agent_for_tool(self, tool_name: str) -> Optional[SubAgent]:
        """Route tool call to appropriate agent"""
        role_map = {
            "write_file": AgentRole.CODER,
            "apply_diff": AgentRole.CODER,
            "execute_python": AgentRole.DEBUGGER,
            "git_checkpoint": AgentRole.DEVOPS,
        }
        target_role = role_map.get(tool_name)
        if target_role:
            return next((a for a in self.agents if a.role == target_role and a.status != "error"), None)
        return None
