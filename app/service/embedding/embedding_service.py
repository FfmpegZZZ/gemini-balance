import datetime
import time
import re # For potential status code parsing from generic errors
from typing import List, Union

import openai
from openai import APIStatusError # Import specific error type
from openai.types import CreateEmbeddingResponse

from app.config.config import settings
from app.log.logger import get_embeddings_logger
from app.database.services import add_error_log, add_request_log # Import DB logging functions

logger = get_embeddings_logger()


class EmbeddingService:

    async def create_embedding(
        self, input_text: Union[str, List[str]], model: str, api_key: str
    ) -> CreateEmbeddingResponse:
        """Create embeddings using OpenAI API with database logging"""
        start_time = time.perf_counter()
        request_datetime = datetime.datetime.now()
        is_success = False
        status_code = None
        response = None
        error_log_msg = ""
        # Prepare request message for logging (truncate if list or long string)
        if isinstance(input_text, list):
            request_msg_log = {"input_truncated": [str(item)[:100] + "..." if len(str(item)) > 100 else str(item) for item in input_text[:5]]}
            if len(input_text) > 5:
                 request_msg_log["input_truncated"].append("...")
        else:
            request_msg_log = {"input_truncated": input_text[:1000] + "..." if len(input_text) > 1000 else input_text}


        try:
            client = openai.OpenAI(api_key=api_key, base_url=settings.BASE_URL)
            response = client.embeddings.create(input=input_text, model=model)
            is_success = True
            status_code = 200
            return response
        except APIStatusError as e:
            is_success = False
            status_code = e.status_code
            error_log_msg = f"OpenAI API error: {e}"
            logger.error(f"Error creating embedding (APIStatusError): {error_log_msg}")
            raise e # Re-raise the specific error
        except Exception as e:
            is_success = False
            error_log_msg = f"Generic error: {e}"
            logger.error(f"Error creating embedding (Exception): {error_log_msg}")
            # Try to parse status code from generic error (less reliable)
            match = re.search(r"status code (\d+)", str(e))
            if match:
                status_code = int(match.group(1))
            else:
                status_code = 500 # Default if parsing fails
            raise e # Re-raise the generic error
        finally:
            end_time = time.perf_counter()
            latency_ms = int((end_time - start_time) * 1000)
            if not is_success:
                 # Log error to database if it failed
                 await add_error_log(
                     gemini_key=api_key, # Using gemini_key parameter name for consistency
                     model_name=model,
                     error_type="openai-embedding",
                     error_log=error_log_msg,
                     error_code=status_code,
                     request_msg=request_msg_log
                 )
            # Log request outcome to database regardless of success/failure
            await add_request_log(
                model_name=model,
                api_key=api_key,
                is_success=is_success,
                status_code=status_code,
                latency_ms=latency_ms,
                request_time=request_datetime
            )
