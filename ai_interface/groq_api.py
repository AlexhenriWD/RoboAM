"""
ai_interface/groq_api.py - Interface for Groq API
"""

import os
import logging
import requests
import json
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class Message:
    """Message for conversation with the LLM"""
    
    def __init__(self, role: str, content: str):
        """
        Initialize a message
        
        Args:
            role (str): Role of the message sender (system, user, assistant)
            content (str): Content of the message
        """
        self.role = role
        self.content = content
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary format for API"""
        return {
            "role": self.role,
            "content": self.content
        }


class GroqAPI:
    """Interface for the Groq API"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "llama3-70b-8192"):
        """
        Initialize the Groq API interface
        
        Args:
            api_key (str, optional): Groq API key, defaults to GROQ_API_KEY env variable
            model (str, optional): Model to use, defaults to llama3-70b-8192
        """
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Groq API key not provided and GROQ_API_KEY environment variable not set")
        
        self.model = model
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def chat_completion(
        self, 
        messages: List[Message], 
        temperature: float = 0.7,
        max_tokens: int = 1024,
        streaming: bool = False
    ) -> Dict[str, Any]:
        """
        Get a chat completion from the Groq API
        
        Args:
            messages (List[Message]): List of messages in the conversation
            temperature (float, optional): Temperature for sampling
            max_tokens (int, optional): Maximum tokens in the response
            streaming (bool, optional): Whether to stream the response
        
        Returns:
            Dict[str, Any]: API response
        """
        if streaming:
            return self._stream_chat_completion(messages, temperature, max_tokens)
        
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            response = requests.post(self.api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling Groq API: {e}")
            raise
    
    def _stream_chat_completion(
        self, 
        messages: List[Message], 
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> Dict[str, Any]:
        """
        Stream a chat completion from the Groq API
        
        Args:
            messages (List[Message]): List of messages in the conversation
            temperature (float, optional): Temperature for sampling
            max_tokens (int, optional): Maximum tokens in the response
        
        Returns:
            Dict[str, Any]: Final API response
        """
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }
        
        try:
            response = requests.post(self.api_url, headers=self.headers, json=payload, stream=True)
            response.raise_for_status()
            
            full_response = {"choices": [{"message": {"content": ""}}]}
            
            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                        data = json.loads(line[6:])
                        content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            full_response["choices"][0]["message"]["content"] += content
                            # Call a callback function here if needed to process streaming content
                            
            return full_response
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error streaming from Groq API: {e}")
            raise


class LLMInterface:
    """High-level interface for interacting with LLMs"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "llama3-70b-8192"):
        """
        Initialize the LLM interface
        
        Args:
            api_key (str, optional): API key for the LLM provider
            model (str, optional): Model to use
        """
        self.groq = GroqAPI(api_key, model)
    
    def query(
        self, 
        system_prompt: str,
        user_message: str,
        conversation_history: List[Dict[str, str]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        """
        Query the LLM
        
        Args:
            system_prompt (str): System prompt to guide the LLM
            user_message (str): User's message to the LLM
            conversation_history (List[Dict[str, str]], optional): Previous conversation
            temperature (float, optional): Temperature for sampling
            max_tokens (int, optional): Maximum tokens in the response
        
        Returns:
            str: LLM's response
        """
        messages = [Message("system", system_prompt)]
        
        # Add conversation history if provided
        if conversation_history:
            for message in conversation_history:
                messages.append(Message(message["role"], message["content"]))
        
        # Add the current user message
        messages.append(Message("user", user_message))
        
        try:
            response = self.groq.chat_completion(messages, temperature, max_tokens)
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error querying LLM: {e}")
            return f"Sorry, I encountered an error: {str(e)}"
    
    def stream_query(
        self, 
        system_prompt: str,
        user_message: str,
        conversation_history: List[Dict[str, str]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        callback = None
    ) -> str:
        """
        Stream a query to the LLM with callback for each chunk
        
        Args:
            system_prompt (str): System prompt to guide the LLM
            user_message (str): User's message to the LLM
            conversation_history (List[Dict[str, str]], optional): Previous conversation
            temperature (float, optional): Temperature for sampling
            max_tokens (int, optional): Maximum tokens in the response
            callback (callable, optional): Function to call with each chunk
        
        Returns:
            str: Full LLM response
        """
        messages = [Message("system", system_prompt)]
        
        # Add conversation history if provided
        if conversation_history:
            for message in conversation_history:
                messages.append(Message(message["role"], message["content"]))
        
        # Add the current user message
        messages.append(Message("user", user_message))
        
        try:
            # This implementation doesn't truly stream with callbacks yet
            # In a real implementation, modify _stream_chat_completion to call the callback
            response = self.groq.chat_completion(messages, temperature, max_tokens, streaming=True)
            content = response["choices"][0]["message"]["content"]
            
            if callback:
                callback(content)
                
            return content
        except Exception as e:
            logger.error(f"Error streaming from LLM: {e}")
            error_message = f"Sorry, I encountered an error: {str(e)}"
            
            if callback:
                callback(error_message)
                
            return error_message