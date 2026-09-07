from __future__ import annotations

from typing import Any, Dict, List


class ResponseCompiler:
    @classmethod
    def compile(
        cls,
        commands: List[Dict[str, Any]],
        engine_response: List[Dict[str, Any]],
    ) -> str:
        if not engine_response:
            return "Команда выполнена, но система не вернула результат."

        answers: List[str] = []

        for index, result in enumerate(engine_response):
            command = commands[index] if index < len(commands) else {}

            answer = cls._compile_single(
                command=command,
                result=result,
            )

            if answer:
                answers.append(answer)

        if not answers:
            return "Команда выполнена."

        return "\n\n".join(answers)

    @classmethod
    def _compile_single(
        cls,
        command: Dict[str, Any],
        result: Dict[str, Any],
    ) -> str:
        # Ответ непосредственного вызова LLM-агента не содержит action.
        if cls._is_agent_response(result):
            return cls._compile_agent_response(result)

        action = result.get("action") or command.get("action")

        if action == "list_agents":
            return cls._compile_list_agents(result)

        if action == "create_agent":
            return cls._compile_create_agent(result)

        if action in {"delete_agent", "remove"}:
            return cls._compile_delete_agent(result)

        if action == "edit_agent":
            return cls._compile_edit_agent(result)

        if action == "extract":
            return cls._compile_extract(result)

        if action == "load":
            return cls._compile_load(result)

        if action == "consolidate":
            return cls._compile_consolidate(result)

        if action == "split":
            return cls._compile_split(result)

        if action == "cancel":
            reason = result.get("reason", "")

            if reason:
                return f"Операция отменена: {reason}"

            return "Операция отменена."

        if action == "no_action":
            return result.get("reason") or "Никаких действий выполнять не требуется."

        if action == "save_system_state":
            return "Состояние системы успешно сохранено."

        if action == "route_document":
            return cls._compile_route_document(result)

        if action == "resolve_logger_conflicts":
            return "Проверка состояния агентов завершена."

        return "Команда успешно выполнена."

    @staticmethod
    def _is_agent_response(result: Dict[str, Any]) -> bool:
        return (
            "agent" in result
            and "status" in result
            and "action" not in result
        )

    @classmethod
    def _compile_agent_response(
        cls,
        result: Dict[str, Any],
    ) -> str:
        agent_name = result.get("agent", "Агент")

        if result.get("status") == "error":
            return cls._compile_agent_error(result)

        answer = result.get("result")

        if answer:
            # Здесь находится настоящий текст,
            # сгенерированный локальной LLM.
            return str(answer)

        return f"{agent_name} завершил обработку запроса."

    @staticmethod
    def _compile_agent_error(
        result: Dict[str, Any],
    ) -> str:
        agent_name = result.get("agent", "Агент")
        error = result.get("error")

        if error == "model_not_configured":
            return (
                f"{agent_name} пока недоступен: "
                "к нему не подключена локальная модель."
            )

        if error == "model_not_found":
            return (
                f"{agent_name} пока недоступен: "
                "файл локальной модели не найден."
            )

        message = result.get("message")

        if message:
            return f"Не удалось выполнить запрос через {agent_name}: {message}"

        return f"Не удалось выполнить запрос через {agent_name}."

    @staticmethod
    def _compile_list_agents(
        result: Dict[str, Any],
    ) -> str:
        agents = result.get("agents", [])
        metadata = result.get("metadata", {})

        if not agents:
            return "В системе пока нет агентов."

        if len(agents) == 1:
            agent_name = agents[0]
            agent_metadata = metadata.get(agent_name, {})
            description = agent_metadata.get("description", "")

            if description:
                return (
                    f"В системе доступен {agent_name} — "
                    f"{description}."
                )

            return f"В системе доступен агент {agent_name}."

        lines = ["В системе доступны следующие агенты:"]

        for agent_name in agents:
            agent_metadata = metadata.get(agent_name, {})
            description = agent_metadata.get("description", "")

            if description:
                lines.append(f"• {agent_name} — {description}")
            else:
                lines.append(f"• {agent_name}")

        return "\n".join(lines)

    @staticmethod
    def _compile_create_agent(
        result: Dict[str, Any],
    ) -> str:
        agent_name = result.get("created")

        if agent_name:
            return f"Агент {agent_name} успешно создан."

        return "Агент успешно создан."

    @staticmethod
    def _compile_delete_agent(
        result: Dict[str, Any],
    ) -> str:
        agent_name = result.get("deleted")

        if agent_name:
            return f"Агент {agent_name} удалён."

        return "Агент удалён."

    @staticmethod
    def _compile_edit_agent(
        result: Dict[str, Any],
    ) -> str:
        agent_name = result.get("agent")

        if agent_name:
            return f"Настройки агента {agent_name} обновлены."

        return "Настройки агента обновлены."

    @classmethod
    def _compile_extract(
        cls,
        result: Dict[str, Any],
    ) -> str:
        answers = result.get("answers", {})

        if not answers:
            return "Агенты не вернули результатов."

        compiled: List[str] = []

        for agent_name, response in answers.items():
            if not isinstance(response, dict):
                compiled.append(f"{agent_name}:\n{response}")
                continue

            answer = cls._compile_agent_response(response)

            compiled.append(
                f"{agent_name}:\n{answer}"
            )

        return "\n\n".join(compiled)

    @staticmethod
    def _compile_load(
        result: Dict[str, Any],
    ) -> str:
        agent_name = result.get("agent", "агента")
        document = result.get("document", {})
        chunks = document.get("chunks_count")

        if chunks is not None:
            return (
                f"Документ загружен для {agent_name}. "
                f"Обработано фрагментов: {chunks}."
            )

        return f"Документ загружен для {agent_name}."

    @staticmethod
    def _compile_consolidate(
        result: Dict[str, Any],
    ) -> str:
        created = result.get("created")
        removed = result.get("removed", [])

        if created and removed:
            return (
                f"Агенты {', '.join(removed)} объединены "
                f"в нового агента {created}."
            )

        if created:
            return f"Агент {created} успешно создан."

        return "Агенты успешно объединены."

    @staticmethod
    def _compile_split(
        result: Dict[str, Any],
    ) -> str:
        source = result.get("removed")
        created = result.get("created", [])

        if source and created:
            return (
                f"Агент {source} разделён на: "
                f"{', '.join(created)}."
            )

        return "Разделение агента завершено."

    @staticmethod
    def _compile_route_document(
        result: Dict[str, Any],
    ) -> str:
        generated = result.get("generated_commands", [])

        if not generated:
            return (
                "Документ обработан, но подходящих "
                "действий для него не найдено."
            )

        return (
            "Документ обработан. "
            f"Сформировано действий: {len(generated)}."
        )