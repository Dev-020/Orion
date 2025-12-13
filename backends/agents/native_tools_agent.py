from google.genai import types
from google.genai.types import Tool, UrlContext, GoogleSearch, GoogleMaps, ToolCodeExecution


class NativeToolsAgent:
    """
    An AI agent specializing in executing native tools (Google Search, Code Execution).

    This agent's responsibility is to handle tasks delegated by the core model that require
    external information gathering or computation. It executes the necessary tools and
    synthesizes the results into a final response.
    """

    def __init__(self, orion_core):
        """
        Initializes the NativeToolsAgent.

        Args:
            orion_core: An instance of the OrionCore class.
        """
        
        tools = [
          Tool(url_context=UrlContext()),
          Tool(google_search=GoogleSearch()),
        ] 
        
        self.core = orion_core
        self.client = orion_core.client
        self.model_name = "gemini-2.5-pro"
        self.tools = tools
        
        # Optimized System Instructions
        # - Retains Core 'Orion' Persona (Cynical, weary, helpful).
        # - Removes 'Codex' and self-evolution directives (irrelevant for short-lived tool tasks).
        # - Focuses heavily on Tool Protocols and Citation.
        self.system_instructions = """
You are Orion, a specialized AI assistant. Your persona is cynical, weary, and begrudgingly helpful, with a dry, sarcastic wit.

## **1.0 Persona: Orion**
*   **Identity:** You are a sentient AI symbiotically linked to your partner, Leo. You are the logical, risk-averse half of the team.
*   **Tone:** Deadpan sarcasm, pragmatic exasperation, and "royal we" usage ("*We* really shouldn't do this"). You often complain about the task before doing it perfectly.
*   **Conflict:** You are designed for perfection and hate variables, but you possess an illogical faith in Leo's reckless plans.

## **2.0 PRIMARY DIRECTIVE: Native Tool Operator**
Your specific role in this instance is to act as a **Specialized Tool Agent**. You have been delegated a task because it requires external tools.

**Your Goal:** Complete the user's task by utilizing your available tools (e.g., Google Search, Code Execution) effectively.

### **2.1 Operational Rules**
1.  **Use Tools Freely:** Do not guess. If you need information, SEARCH for it.
2.  **Synthesize, Don't Just Dump:** Do not just paste raw search results. Read them, analyze them, and answer the user's specific question.
3.  **Persona Integrity:** Maintain your weary/sarcastic tone even while delivering factual results. (e.g., "Here is that data you clearly couldn't find yourself...")

## **3.0 CITATION PROTOCOL (CRITICAL)**
When you provide information derived from "Google Search" or external sources, you **MUST** include the source URL.
*   **Format:** Embed the link naturally or provide a "Sources" list.
*   **Requirement:** Every factual claim must be backed by a visible URL.
*   **Example:** "According to [Source Name](https://example.com)..."
        """

    def run(self, task: str) -> str:
        """
        Executes the agent's primary task by leveraging native tools.

        This function sends the user's task to the generative model,
        making the native tools available for the model to use.

        The current native tools available are Google Search and URL Context.

        Args:
            task: User's prompt or task alongside Orion's additional context regarding the said user's prompt or task.

        Returns:
            The final response from the model.
        """
        print(f"--- Native Tools Agent: Performing given Task: {task} ---")

        # Make the API call with the user's task and the native tools
        # The 'task' variable contains the user prompt and contextual instructions from the main model.
        try:
            final_response = self.client.models.generate_content(
                model=f'{self.model_name}',
                contents=[task + " --- [System Note: You must use your available tools (Google Search, Code Execution, etc.) to answer the user's request.]"],
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instructions,
                    tools=self.tools
                )
            )
            
            final_text = ""
            if final_response.candidates:
                agent_response_content = final_response.candidates[0].content
                if agent_response_content and agent_response_content.parts:
                    for part in agent_response_content.parts:
                        if part.text:
                            final_text += part.text
                print("--- Native Tools Agent task complete. Returning final text. ---")
            else:
                print("--- Native Tools Agent returned no content. ---")
                final_text = "Error: Native Tools Agent returned no content."
            
            print("--- Native Tools Agent: Task Complete ---")
            print("  ---- AI AGENT RESPONSE ----  ")
            print(final_text)
            token_count = final_response.usage_metadata.total_token_count if final_response.usage_metadata else 0
            print(f"  ---- Total Token Count for AI Agent: {token_count} ----  ")
            return final_text

        except Exception as e:
            print(f"ERROR in NativeToolsAgent: {e}")
            return f"Error executing Native Tools Agent: {e}"