import json
import requests
import time
from .tim_pydantic import type_to_response_format_param
from typing import Dict

class Usage:
    def __init__(
            self,
            prompt_tokens: int = 0,
            completion_tokens: int = 0,
            total_tokens: int = 0
        ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        
    def update(
            self,
            prompt_tokens: int = 0,
            completion_tokens: int = 0,
            total_tokens: int = 0
        ):
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += total_tokens

class TIMResponse:
    def __init__(
            self,
            latency: float,
            content: Dict,
            usage: Usage = None
        ):
            self.latency = latency
            self.content = content
            self.usage = usage
    
    def __str__(self) -> str:
        """Make TIMResponse printable and readable."""
        lines = []
        lines.append("TIMResponse:")
        lines.append(f"  Latency: {self.latency:.3f}s")
        
        # Format usage information if available
        if self.usage:
            lines.append(f"  Usage:")
            lines.append(f"    Prompt tokens: {self.usage.prompt_tokens}")
            lines.append(f"    Completion tokens: {self.usage.completion_tokens}")
            lines.append(f"    Total tokens: {self.usage.total_tokens}")
        else:
            lines.append("  Usage: Not available")
        
        # Format content
        lines.append("  Content:")
        # Try to parse as JSON first, otherwise just display as string
        try:
            parsed_content = json.loads(self.content)
            answer = parsed_content['answer']
            lines.append(f"    {answer}")
        except (json.JSONDecodeError, TypeError):
            lines.append(f"    Invalid JSON")
        
        return '\n'.join(lines)


def tim_streaming(
        openai_client,
        model,
        messages,
        tools,
        reasoning_grammar_model
    ):
    """Test the /v1/agent/parse endpoint with streaming enabled."""
    
    # Reasoning grammar from test_asm_call()
    reasoning_grammar = type_to_response_format_param(
        reasoning_grammar_model
    )['json_schema']['schema']
    
    usage = Usage()

    # try:
    if True:
        # Make streaming request
        response = openai_client.chat.completions.create(
            model = model,
            messages = messages,
            max_completion_tokens = 10000,
            temperature = 0.6,
            top_p = 0.95,
            tools = tools,
            response_format = reasoning_grammar,
            stream = True
        )
        
        # Process streaming response
        chunk_count = 0
        start_time = time.time()
        full_content = ""  # Collect all content for final JSON
        
        for chunk in response:
            chunk_count += 1
            choices = chunk.choices
            if choices is not None and len(choices) > 0:
                delta = choices[0].delta
                if delta.content is not None:
                    content_piece = delta.content
                    full_content += content_piece
                    # print(content_piece, end='', flush=True)  # Flush output immediately
            if chunk.usage is not None:
                usage_chunk = chunk.usage
                usage.update(
                    prompt_tokens=usage_chunk.prompt_tokens,
                    completion_tokens=usage_chunk.completion_tokens,
                    total_tokens=usage_chunk.total_tokens
                )

        # open('tmp/final_answer_raw.json', 'w').write(full_content)
        return TIMResponse(
            latency = time.time() - start_time,
            content = full_content,
            usage = usage
        )
        
    # except requests.exceptions.RequestException as e:
    #     print(f"Request error: {e}")
    # except KeyboardInterrupt:
    #     print("\nTest interrupted by user")
    # except Exception as e:
    #     print(f"Unexpected error: {e}")

def tim_streaming_legacy(model, messages, tools, reasoning_grammar_model):
    """Test the /v1/agent/parse endpoint with streaming enabled."""
    
    # Server URL - adjust if running on different host/port
    base_url = "http://localhost:8001"  # Assuming FastAPI runs on default port
    endpoint = f"{base_url}/v1/agent/parse"
    
    # Sampling parameters from test_asm_call()
    sampling_params = {
        "top_p": 0.95,
        "max_completion_tokens": 10000,
        "temperature": 0.6,
        "tools": tools
    }
    
    # Reasoning grammar from test_asm_call()
    reasoning_grammar = type_to_response_format_param(
        reasoning_grammar_model
    )['json_schema']['schema']
    
    # Request payload for streaming
    payload = {
        "model": model,  # Adjust model name as needed
        "messages": messages,
        "stream": True,
        "sampling_params": sampling_params,
        "reasoning_grammar": reasoning_grammar
    }
    
    print("Testing /v1/agent/parse endpoint with streaming...")
    print(f"Endpoint: {endpoint}")
    print("\n" + "="*50)
    print("Streaming response:")
    print("="*50)
    
    try:
        # Make streaming request
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=300  # 5 minute timeout
        )
        
        if response.status_code != 200:
            print(f"Error: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        # Process streaming response
        chunk_count = 0
        start_time = time.time()
        full_content = ""  # Collect all content for final JSON
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                
                # Skip empty lines and comments
                if not line_str.strip() or line_str.startswith(':'):
                    continue
                
                # Parse SSE format
                if line_str.startswith('data: '):
                    data_str = line_str[6:]  # Remove 'data: ' prefix
                    
                    if data_str.strip() == '[DONE]':
                        print("\n" + "="*50)
                        print("Stream completed")
                        break
                    
                    try:
                        chunk_data = json.loads(data_str)
                        chunk_count += 1
                        
                        # Extract content from the chunk
                        choices = chunk_data.get('choices', [])
                        if choices:
                            delta = choices[0].get('delta', {})
                            content = delta.get('content', '')
                            finish_reason = choices[0].get('finish_reason')
                            
                            if content:
                                print(content, end='', flush=True)  # Flush output immediately
                                full_content += content  # Collect for final JSON
                            
                            if finish_reason:
                                print(f"\nFinish reason: {finish_reason}", flush=True)
                    
                    except json.JSONDecodeError as e:
                        print(f"\nError parsing chunk JSON: {e}", flush=True)
                        print(f"Raw data: {data_str}", flush=True)
        
        end_time = time.time()
        print(f"\nTotal chunks received: {chunk_count}", flush=True)
        print(f"Total time: {end_time - start_time:.2f} seconds", flush=True)
        
        # Save the final answer as JSON with indents
        if full_content.strip():
            try:
                # Parse the complete content as JSON
                final_answer = json.loads(full_content)
                return final_answer

                # Save to tmp/final_answer.json with indents
                # with open('tmp/final_answer.json', 'w') as f:
                #     json.dump(final_answer, f, indent=4)

                # print(f"Final answer saved to tmp/final_answer.json", flush=True)
                # print(f"Content length: {len(full_content)} characters", flush=True)
                
            except json.JSONDecodeError as e:
                print(f"Warning: Could not parse final content as JSON: {e}", flush=True)
                print(f"Raw content preview: {full_content[:200]}...", flush=True)
                
                # Save raw content for debugging
                with open('tmp/final_answer_raw.json', 'w') as f:
                    f.write(full_content)
                print("Raw content saved to tmp/final_answer_raw.txt", flush=True)
        
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")

