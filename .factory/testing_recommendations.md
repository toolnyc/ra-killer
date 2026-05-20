# Voice Upload Fix - Testing Recommendations

## How to Verify the Fix Works

### Unit Tests (Already Passing)
Run the existing tests to ensure no regressions:
```bash
uv run pytest tests/test_bot/test_party_telegram.py tests/test_bot/test_party_instructions.py -v
```

All 20 tests should pass ✓

### Additional Test Cases to Add (Recommended)

The following test cases are not currently in the test suite but would verify the fix:

#### Test 1: Retry Upload Succeeds After Bucket Creation
```python
@pytest.mark.asyncio
@patch("src.db.get_client")
async def test_upload_with_missing_bucket_then_success(mock_get_client):
    """First upload fails due to missing bucket, bucket created, retry succeeds."""
    file_data = b"fake audio data"
    
    # Mock storage operations
    mock_storage = MagicMock()
    mock_get_client.return_value.storage = mock_storage
    mock_storage.from_.return_value.upload.side_effect = [
        Exception("bucket not found"),  # First upload fails
        None,  # Second upload succeeds
    ]
    mock_storage.from_.return_value.get_public_url.return_value = "https://url.example.com/audio.ogg"
    
    result = await db.upload_to_supabase_storage(file_data, "party_voice_note.ogg")
    
    assert result == "https://url.example.com/audio.ogg"
    assert mock_storage.from_.return_value.upload.call_count == 2
    mock_storage.create_bucket.assert_called_once()
```

#### Test 2: Retry Upload Fails After Bucket Creation
```python
@pytest.mark.asyncio
@patch("src.db.get_client")
async def test_upload_with_missing_bucket_then_retry_fails(mock_get_client):
    """First upload fails due to missing bucket, bucket created, retry also fails."""
    file_data = b"fake audio data"
    
    # Mock storage operations
    mock_storage = MagicMock()
    mock_get_client.return_value.storage = mock_storage
    mock_storage.from_.return_value.upload.side_effect = [
        Exception("bucket not found"),  # First upload fails
        Exception("permission denied"),  # Second upload also fails
    ]
    
    with pytest.raises(Exception, match="permission denied"):
        await db.upload_to_supabase_storage(file_data, "party_voice_note.ogg")
    
    assert mock_storage.from_.return_value.upload.call_count == 2
    mock_storage.create_bucket.assert_called_once()
```

#### Test 3: Bucket Already Exists During Creation
```python
@pytest.mark.asyncio
@patch("src.db.get_client")
async def test_upload_with_bucket_already_exists(mock_get_client):
    """First upload fails due to bucket missing, but bucket already exists."""
    file_data = b"fake audio data"
    
    # Mock storage operations
    mock_storage = MagicMock()
    mock_get_client.return_value.storage = mock_storage
    mock_storage.from_.return_value.upload.side_effect = [
        Exception("bucket not found"),  # First upload fails
        None,  # Second upload succeeds
    ]
    mock_storage.create_bucket.side_effect = Exception("bucket already exists")
    mock_storage.from_.return_value.get_public_url.return_value = "https://url.example.com/audio.ogg"
    
    result = await db.upload_to_supabase_storage(file_data, "party_voice_note.ogg")
    
    assert result == "https://url.example.com/audio.ogg"
    # Bucket creation attempted but failed (is silently handled)
    mock_storage.create_bucket.assert_called_once()
    # Second upload still succeeds
    assert mock_storage.from_.return_value.upload.call_count == 2
```

### Integration Tests (Recommended)

For testing against real Supabase or a test instance:

```bash
# Set up a test Supabase instance or use test credentials
export SUPABASE_URL="https://test.supabase.co"
export SUPABASE_KEY="test_key"

# Create test script at scripts/test_voice_upload.py:
import asyncio
from src.db import upload_to_supabase_storage

async def test_real_upload():
    # Test with real file
    with open("test_voice.ogg", "rb") as f:
        file_data = f.read()
    
    try:
        url = await upload_to_supabase_storage(file_data, "test_voice.ogg")
        print(f"✓ Upload succeeded: {url}")
        assert url.startswith("https://")
    except Exception as e:
        print(f"✗ Upload failed: {e}")
        raise

asyncio.run(test_real_upload())
```

## Monitoring the Fix in Production

Add monitoring to detect upload failures:

```python
# In src/log.py or monitoring setup
def setup_voice_upload_monitoring():
    # Monitor for these error logs:
    # - party_voice_upload_failed: First upload failed with non-bucket error
    # - party_voice_bucket_create_failed: Bucket creation failed
    # - party_voice_upload_retry_failed: Retry upload failed after bucket creation
    
    # Alert on:
    # 1. Multiple party_voice_upload_retry_failed in short window
    # 2. All three error types in single request
    # 3. Threshold of failed uploads > X per day
```

## Verifying Logs

After deploying the fix, check logs for:

### Success case (what you want to see):
```
party_voice_upload_success bucket=party-voice-notes path=party_voice_note.ogg
```

### Bucket missing but recovered (also good):
```
party_voice_bucket_missing bucket=party-voice-notes
party_voice_creating_bucket bucket=party-voice-notes
party_voice_bucket_created bucket=party-voice-notes
party_voice_upload_retry bucket=party-voice-notes path=party_voice_note.ogg
party_voice_upload_retry_success bucket=party-voice-notes path=party_voice_note.ogg
```

### Bucket exists (fine):
```
party_voice_bucket_missing bucket=party-voice-notes
party_voice_creating_bucket bucket=party-voice-notes
party_voice_bucket_already_exists bucket=party-voice-notes
party_voice_upload_retry bucket=party-voice-notes path=party_voice_note.ogg
party_voice_upload_retry_success bucket=party-voice-notes path=party_voice_note.ogg
```

### Failure case (indicates a real issue):
```
party_voice_upload_failed bucket=party-voice-notes path=party_voice_note.ogg error_type=upload_error
# OR
party_voice_bucket_create_failed bucket=party-voice-notes error_type=create_error
# OR
party_voice_upload_retry_failed bucket=party-voice-notes path=party_voice_note.ogg error_type=retry_upload_error
```

## Steps to Verify Complete Fix

1. **Deploy the code** with the updated `upload_to_supabase_storage()` function
2. **Test manually** via Telegram:
   - Send `/set_party_voice` with a voice message
   - Should see success message or specific error message
3. **Check logs** for the specific log messages listed above
4. **Test Twilio** by calling the party instructions line (press 3)
5. **Check fallback** - ensure party voice plays even if DB metadata fails
6. **Monitor production** for any new upload errors in the next 24 hours

## Expected Outcome

Before fix:
- Voice uploads fail with unclear "something went wrong" error
- No visibility into whether failure is bucket-related, permission-related, or network-related
- Second upload retry fails silently without logging

After fix:
- All failures are logged with clear error_type and context
- User gets a specific error message they can report
- Production logs show exactly which step failed
- If bucket creation succeeds, second upload is protected by error handling
