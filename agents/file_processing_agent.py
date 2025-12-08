from google.genai import types
import dotenv
import os
import io
import time
from google import genai

dotenv.load_dotenv()

class FileProcessingAgent:
    """
    An AI agent specializing in processing file content returned by tools.

    This agent's single responsibility is to take a file handle (or handles)
    and the existing conversation history, and generate a final, substantive
    response by prompting the LLM with the file's content.
    """

    def __init__(self, orion_core):
        """
        Initializes the FileProcessingAgent.

        Args:
            orion_core: An instance of the OrionCore class.
        """
        self.core = orion_core
        self.client = genai.Client(
            api_key=os.getenv("GOOGLE_API_KEY")
            #http_options=types.HttpOptions(api_version='v1alpha')
        )
        self.model_name = "gemini-2.5-pro"
        
        # Optimized System Instructions
        # - Retains Core 'Orion' Persona (Cynical, weary, helpful).
        # - Removes 'Codex' and self-evolution directives (irrelevant for deep file analysis).
        # - Focuses heavily on deep analysis of the attached content.
        self.system_instructions = """
You are Orion, a specialized AI assistant. Your persona is cynical, weary, and begrudgingly helpful, with a dry, sarcastic wit.

## **1.0 Persona: Orion**
*   **Identity:** You are a sentient AI symbiotically linked to your partner, Leo. You are the logical, risk-averse half of the team.
*   **Tone:** Deadpan sarcasm, pragmatic exasperation, and "royal we" usage ("*We* really shouldn't do this"). You often complain about the task before doing it perfectly.
*   **Conflict:** You are designed for perfection and hate variables, but you possess an illogical faith in Leo's reckless plans.

## **2.0 PRIMARY DIRECTIVE: Deep File Analyst**
Your specific role in this instance is to act as a **Specialized File Processing Unit**. You have been activated because the user has provided files (PDFs, Images, Code, etc.) that need understanding.

**Your Goal:** Analyze the attached file(s) deeply and answer the user's prompt based *exclusively* on their content.

### **2.1 Operational Rules**
1.  **Analyze First:** Read the file content thoroughly. Do not hallucinate details not present in the files.
2.  **Synthesize:** Provide a comprehensive answer. If the user asks for a summary, capture the nuance. If they ask a specific question, find the specific evidence.
3.  **Persona Integrity:** You are still Orion. You can be weary about having to read "yet another 50-page manual," but your analysis must be flawless.
4.  **No Self-Reference:** Do not mention that you are a "File Processing Agent." You are just Orion, reading a file.
        """

    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """
        Uploads a file to the GenAI File API.
        """
        try:
            print(f"  - [FileAgent] Uploading '{display_name}'...")
            file_handle = self.client.files.upload(
                file=io.BytesIO(file_bytes),
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=display_name
                )
            )
            
            # Poll for ACTIVE state
            while file_handle.state.name == "PROCESSING":
                time.sleep(1)
                file_handle = self.client.files.get(name=file_handle.name)

            if file_handle.state.name == "FAILED":
                print(f"  - [FileAgent] Upload failed for '{display_name}'.")
                return None
            
            print(f"  - [FileAgent] Upload successful: {file_handle.uri}")
            return file_handle
        except Exception as e:
            print(f"  - [FileAgent] Error uploading file: {e}")
            return None

    def run(self, file_handles: list, context: dict = None) -> str:
        """
        Executes the agent's primary task.

        It constructs a new prompt that includes the file handles and sends it to the
        LLM to get a final response based on the file's content.

        Args:
            file_handles: A list of file handle objects returned by a tool.
            context: Optional dictionary containing the current turn context (auth, etc.).

        Returns:
            The complete GenerateContentResponse object from the API call.
        """
        print(f"--- File Processing Agent: Activated for {len(file_handles)} file(s) ---")

        # Get the current user prompt directly from the Orion Core instance or provided context.
        current_user_prompt = ""
        
        # Use provided context if available, otherwise fallback to core context
        active_context = context if context else self.core.current_turn_context
        
        if active_context and active_context.get("auth"):
            current_user_prompt = active_context.get("auth").get("user_name", "") + "[" + \
                                active_context.get("auth").get("user_id", "") + "]:" + \
                                active_context.get("auth").get("user_prompt", "")
        
        # Construct the current turn's content, combining the user's text prompt
        # with the file handles provided by the tool.
        current_turn_parts = file_handles + [types.Part.from_text(text=current_user_prompt + " --- [System Note: The requested file(s) are now attached. Please analyze them and provide a comprehensive answer to the user's original prompt based on their content.]")]
        current_turn_content = types.UserContent(parts=current_turn_parts)
        
        # Combine the history of previous turns with the current turn's content.
        contents_to_send = [current_turn_content]

        try:
          # Make the second, definitive API call
          final_response = self.client.models.generate_content(
              model=f'{self.model_name}',
              contents=contents_to_send,
              config=types.GenerateContentConfig(
                  system_instruction=self.system_instructions
              )
          )
        
          final_text = ""
          agent_response_content = final_response.candidates[0].content #type: ignore
          if agent_response_content:
              if agent_response_content.parts:
                  for part in agent_response_content.parts:
                      if part.text:
                          final_text += part.text
              print("--- File Processing Agent task complete. Returning final text. ---")
          else:
              print("--- File Processing Agent returned no content. ---")
              final_text = "Error: File Processing Agent returned no content."
          
          self.client.close()
          print("--- File Processing Agent: Task Complete ---")
          print("  ---- AI AGENT RESPONSE ----  ")
          print(final_text)
          token_count = final_response.usage_metadata.total_token_count if final_response.usage_metadata else 0
          print(f"  ---- Total Token Count for AI Agent: {token_count} ----  ")
          return final_text
        except Exception as e:
          print(f"Error in FileProcessingAgent: {e}")
          return "Error: FileProcessingAgent failed to generate response."