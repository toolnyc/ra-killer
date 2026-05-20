# PROPOSED FIX FOR VOICE NOTE UPLOAD ISSUE
# File: src/db.py
# Function: upload_to_supabase_storage()

# BEFORE (Current Code - BUGGY):
# ==============================
# async def upload_to_supabase_storage(file_data: bytes, filename: str = PARTY_VOICE_FILENAME) -> str:
#     """Upload audio file to Supabase Storage and return public URL.
#     
#     Args:
#         file_data: Binary audio file content
#         filename: Original filename (e.g., "party_voice_note.ogg")
#     
#     Returns:
#         Public HTTPS URL to the uploaded file
#     """
#     import asyncio
#     bucket = PARTY_VOICE_BUCKET
#     path = filename
#     
#     # Upload file in thread pool to avoid blocking the event loop
#     # (Supabase storage API calls are synchronous)
#     def _upload() -> str:
#         storage = get_client().storage
#         try:
#             storage.from_(bucket).upload(
#                 path=path,
#                 file=file_data,
#                 file_options={"content-type": "audio/ogg", "upsert": "true"},
#             )
#         except Exception as exc:
#             if not _is_missing_bucket_error(exc):
#                 raise
#             try:
#                 storage.create_bucket(bucket, options={"public": True})
#             except Exception as create_exc:
#                 if not _is_bucket_exists_error(create_exc):
#                     raise
#             storage.from_(bucket).upload(  # <-- SECOND UPLOAD NOT PROTECTED!
#                 path=path,
#                 file=file_data,
#                 file_options={"content-type": "audio/ogg", "upsert": "true"},
#             )
#         return storage.from_(bucket).get_public_url(path)
#
#     loop = asyncio.get_event_loop()
#     return await loop.run_in_executor(None, _upload)


# AFTER (FIXED CODE):
# ===================

async def upload_to_supabase_storage(file_data: bytes, filename: str = PARTY_VOICE_FILENAME) -> str:
    """Upload audio file to Supabase Storage and return public URL.
    
    Args:
        file_data: Binary audio file content
        filename: Original filename (e.g., "party_voice_note.ogg")
    
    Returns:
        Public HTTPS URL to the uploaded file
        
    Raises:
        Exception: If upload fails after all retry attempts
    """
    import asyncio
    bucket = PARTY_VOICE_BUCKET
    path = filename
    
    # Upload file in thread pool to avoid blocking the event loop
    # (Supabase storage API calls are synchronous)
    def _upload() -> str:
        storage = get_client().storage
        
        # First attempt: try to upload directly
        try:
            storage.from_(bucket).upload(
                path=path,
                file=file_data,
                file_options={"content-type": "audio/ogg", "upsert": "true"},
            )
            logger.debug("party_voice_upload_success", bucket=bucket, path=path)
            return storage.from_(bucket).get_public_url(path)
        except Exception as exc:
            # If not a bucket error, fail immediately
            if not _is_missing_bucket_error(exc):
                logger.exception("party_voice_upload_failed", bucket=bucket, path=path, error_type="upload_error")
                raise
            
            logger.info("party_voice_bucket_missing", bucket=bucket)
        
        # Second attempt: create bucket and retry upload
        try:
            logger.info("party_voice_creating_bucket", bucket=bucket)
            storage.create_bucket(bucket, options={"public": True})
            logger.info("party_voice_bucket_created", bucket=bucket)
        except Exception as create_exc:
            # If bucket already exists, that's fine - proceed to retry upload
            if not _is_bucket_exists_error(create_exc):
                logger.exception("party_voice_bucket_create_failed", bucket=bucket, error_type="create_error")
                raise
            logger.info("party_voice_bucket_already_exists", bucket=bucket)
        
        # Third attempt: retry upload after bucket handling
        try:
            logger.info("party_voice_upload_retry", bucket=bucket, path=path)
            storage.from_(bucket).upload(
                path=path,
                file=file_data,
                file_options={"content-type": "audio/ogg", "upsert": "true"},
            )
            logger.info("party_voice_upload_retry_success", bucket=bucket, path=path)
            return storage.from_(bucket).get_public_url(path)
        except Exception as retry_exc:
            logger.exception("party_voice_upload_retry_failed", bucket=bucket, path=path, error_type="retry_upload_error")
            raise
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _upload)


# EXPLANATION OF CHANGES:
# =======================
# 1. Moved the first upload into a try-except that returns early on success
#    - Clearer control flow
#    - Logs successful upload
#
# 2. Separated bucket creation logic from the first exception handler
#    - First exception handler is for "first upload failed" 
#    - Follows immediately with bucket creation attempt
#    - Returns early with the URL if first upload succeeds
#
# 3. Wrapped the second upload attempt in its own try-except
#    - Previously unprotected - this was the bug!
#    - Now logs and re-raises if it fails
#    - Allows caller to handle the error appropriately
#
# 4. Added comprehensive logging at each step
#    - debug: successful operations
#    - info: bucket operations and retries
#    - exception: all failure paths
#    - Allows production monitoring to understand what's failing
#
# 5. Added logging to exception handlers with error_type labels
#    - Distinguishes between different failure modes
#    - Makes production debugging easier
#
# WHY THIS FIXES THE ISSUE:
# =========================
# The original code left the second upload attempt unprotected inside the
# first exception handler. If it failed, the exception would propagate
# uncaught, causing the entire operation to fail with an unclear error.
#
# The fixed code:
# - Handles all three paths (initial success, bucket missing, retry)
# - Logs each step so we can see exactly where failures occur
# - Properly propagates errors while capturing context
# - Makes the flow explicit rather than implicit
#
# This doesn't prevent upload failures, but it:
# 1. Ensures they're properly logged and traceable
# 2. Prevents silent cascading failures
# 3. Makes it clear when bucket creation vs upload is the problem
# 4. Allows the Telegram command handler to give better feedback to users
