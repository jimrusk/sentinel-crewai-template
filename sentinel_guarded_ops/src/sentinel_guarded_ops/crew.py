from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from sentinel_guarded_ops.tools.guarded_actions import ExecuteGuardedActionTool
from sentinel_guarded_ops.tools.sentinel_tools import (
    SentinelAuditStatusTool,
    SentinelEvaluateActionTool,
)

# Sentinel Guarded Ops crew.
#
# Pattern demonstrated here: an operations agent proposes actions, but every
# consequential action passes through Sentinel (Aridon's pre-execution
# authorization layer) BEFORE anything executes. The agent's only execution
# tool, execute_guarded_action, re-checks the gate internally, so held or
# denied actions cannot execute even if the agent skips the pre-check.


@CrewBase
class SentinelGuardedOps:
    """Sentinel Guarded Ops crew"""

    # Learn more about YAML configuration files here:
    # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
    # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def operations_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config["operations_specialist"],
            tools=[SentinelEvaluateActionTool(), ExecuteGuardedActionTool()],
            verbose=True,
        )

    @agent
    def compliance_reporter(self) -> Agent:
        return Agent(
            config=self.agents_config["compliance_reporter"],
            tools=[SentinelAuditStatusTool()],
            verbose=True,
        )

    @task
    def process_requests_task(self) -> Task:
        return Task(
            config=self.tasks_config["process_requests_task"],
        )

    @task
    def gate_report_task(self) -> Task:
        return Task(
            config=self.tasks_config["gate_report_task"],
            output_file="sentinel_gate_report.md",
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Sentinel Guarded Ops crew"""
        return Crew(
            agents=self.agents,  # Automatically created by the @agent decorator
            tasks=self.tasks,  # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
        )
