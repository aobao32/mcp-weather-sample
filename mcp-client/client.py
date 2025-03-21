import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anthropic import Anthropic
from dotenv import load_dotenv

import boto3
import json
from loguru import logger

#model_id = 'anthropic.claude-3-5-sonnet-20241022-v2:0'
model_id = 'us.anthropic.claude-3-5-sonnet-20240620-v1:0'

system_prompt = '你是一个智能聊天机器人，以生成方式回答问题。当、且仅当用户提问涉及到美国的天气时候，使用模型的Tool use能力进行互动。如果是询问美国之外的其他国家和地区的天气问题，那么答复“目前只能在线获取美国的天气，不能获取其他国家天气”。此外如果用户一次提问涉及到多个美国的地区天气信息查询，那么需要多次tooluse，此时每次response只生成一条tooluse信息，依次执行。。'

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()

    async def connect_to_server(self, server_script_path: str):
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")
        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()

        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        messages = [{
            "role": "user",
            "content": [{"text": query}]
        }]
        # list tool
        response = await self.session.list_tools()
        available_tools = [{
            "toolSpec": {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": {
                    "json": json.loads(tool.inputSchema) if isinstance(tool.inputSchema, str) else tool.inputSchema
                }
            }
        } for tool in response.tools]
        
        # for debug
        print("Prepare - initial tool")
        logger.debug(available_tools)
        print("Prepare - system prompt")
        logger.debug(system_prompt)
        print("Prepare - initial message")
        logger.debug(messages)
        print("connecting to LLM...")
        
        client = boto3.client('bedrock-runtime', region_name='us-west-2')
        response = client.converse(
            modelId=model_id,
            system=[{"text" : system_prompt}],
            messages=messages,
            toolConfig={
                "tools": available_tools
            }
        )
        final_text = []
        output_message = response.get('output', {}).get('message', {})
        stop_reason = response.get('stopReason', '')
        messages.append(output_message) # 将响应消息添加到消息列表中以保持对话上下文
        
        # stop reason - end turn - output final message
        if stop_reason == 'end_turn':
            if 'content' in output_message:
                for content_item in output_message['content']:
                    if 'text' in content_item:
                        logger.info("触发Endturn")
                        final_text.append(content_item['text'])
                        logger.info(final_text)
        # for debug
        i = 1
        print("Step", i, " - LLM output message")
        logger.debug(output_message)
        print("Step", i, " - stop reason")
        logger.debug(stop_reason)
        #print("Step", i, " - messages consolidated with chat history")
        #logger.debug(messages)
                
        # another Step of tool use until get "end_turn" singal from LLM output
        loopflag = 0
        while stop_reason == 'tool_use':
            if 'content' in output_message:
                for content_item in output_message['content']:
                    if 'text' in content_item:
                        if loopflag != 1 :
                            logger.info("触发Tooluse第一步提取text")
                            final_text.append(content_item['text'])
                            logger.info(final_text)
                        else:
                            logger.info("这是循环，不重复写入")
                    elif 'toolUse' in content_item:
                        tool = content_item['toolUse']
                        tool_name = tool['name']
                        tool_input = tool['input']
                        tool_use_id = tool['toolUseId']
                        
                        # for debug
                        print("executing tools...")
                        
                        # 执行工具调用
                        final_text.append(f"[调用工具 {tool_name}]")
                        result = await self.session.call_tool(tool_name, tool_input)
                        tool_result = {
                            "toolUseId": tool_use_id,
                            "content": [{"text": str(result.content[0])}]
                        } 
                        
                        # 添加tooluse结果到历史消息
                        tool_result_message = {
                            "role": "user",
                            "content": [
                                {
                                    "toolResult": tool_result
                                }
                            ]
                        }
                        messages.append(tool_result_message)
                        
                        # for debug
                        i=i+1
                        print("Step", i, " - Tool to be executed")
                        logger.debug(tool)
                        print("Step", i, " - Tool execution result")
                        logger.debug(tool_result)
                        #print("Step", i, " - messages consolidated with chat history")
                        #logger.debug(messages)
                        
                        # tool use ends here
                        print("connecting to LLM...")
                                            
                        response = client.converse(
                            modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
                            messages=messages,
                            toolConfig={
                                "tools": available_tools
                            }
                        )
                        output_message = response.get('output', {}).get('message', {})
                        stop_reason = response.get('stopReason', '')
                        messages.append(output_message)
                        
                        # for debug
                        i=i+1
                        print("Step", i, " - LLM work with tool result - Output")
                        logger.debug(output_message)
                        print("Step", i, " - stop reason")
                        logger.debug(stop_reason)
                        #print("Step", i, " - messages consolidated with chat history")
                        #logger.debug(messages)
                                
                        if 'content' in output_message:
                            for next_content in output_message['content']:
                                if 'text' in next_content:
                                    final_text.append(next_content['text'])
                                    loopflag = 1 # 避免循环重复加入模型返回信息到final output message里边
                                    logger.info(final_text)
            # while loop - stop here
            
        tool={}
        tool_result={}
        return "\n".join(final_text)
    
    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(query)
                
                # for debug
                print ("\n### Final output ###")
                print("\n", response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: uv run client.py /path-to-mcp-server/yourserver.py")
        sys.exit(1)
        
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())