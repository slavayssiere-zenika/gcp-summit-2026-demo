import asyncio
import os
import sys
import logging

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_tester")

try:
    from agent_api.mcp_client import get_users_mcp
except ImportError as e:
    logger.error(f"Failed to import mcp_client: {e}")
    sys.exit(1)

async def test_connectivity():
    logger.info("Starting MCP Connectivity Test...")
    
    users_api_url = os.getenv("USERS_API_URL", "http://users_api:8000")
    logger.info(f"Target Users API URL: {users_api_url}")
    
    try:
        logger.info("Attempting to get Users MCP client...")
        mcp = await get_users_mcp()
        
        logger.info("Attempting to call 'list_users' tool...")
        # Note: We are testing the raw MCP call, not the agent wrapper
        result = await mcp.call_tool("list_users", {"skip": 0, "limit": 1})
        
        if result:
            logger.info("SUCCESS: Received result from 'list_users'")
            logger.info(f"Result snippet: {str(result)[:200]}...")
        else:
            logger.warning("WARNING: Received empty result from 'list_users'")
            
    except Exception as e:
        logger.error(f"CRITICAL ERROR during MCP test: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connectivity())
