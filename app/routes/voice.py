# app/routes/voice.py

import os
import tempfile
from fastapi import APIRouter, Query, Depends, UploadFile, File, HTTPException
from app.voice.recognizer import recognize_from_file
from app.core.homeassistant import LightControl
from app import models, auth, schemas
from app.voiceassistant.va import VoiceAssistant
from app.voiceassistant.llm import query_llm
from app.voiceassistant.location import query_resident_location, query_delivery_status
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/voice", tags=["Voice Assistant"])


@router.get("/command")
async def voice_command(
    text: str = Query(..., description="Command text from user"),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a voice command as text, parses intent, and executes action via Home Assistant.
    Example: /voice/command?text=turn on the guest room light
    Also handles resident location queries: "where is Reece", "where are my kids", etc.
    """
    execute_command = await VoiceAssistant.search_commands(text)

    if execute_command and execute_command.get("output_json", {}).get("entity_id"):
        execute_result = await VoiceAssistant.execute_command(execute_command)
        return {"success": True, "message": "Command executed", "response": execute_result}

    # Check for resident location queries before LLM fallback
    location_response = await query_resident_location(text, db)
    if location_response:
        return {"success": True, "message": "Resident location", "response": location_response}

    # Check for recent deliveries queries
    delivery_response = await query_delivery_status(text, db)
    if delivery_response:
        return {"success": True, "message": "Delivery status", "response": delivery_response}

    response = await query_llm(text)
    return {"success": True, "message": "Response from LLM", "response": response}


@router.post("/stt")
async def speech_to_text(
    file: UploadFile = File(..., description="M4A or MP3 audio file for speech recognition"),
    execute_command: bool = Query(False, description="Whether to execute the recognized command"),
    min_confidence: float = Query(0.7, ge=0.0, le=1.0, description="Minimum confidence threshold (0.0-1.0). Recognition below this will be rejected. Default: 0.7"),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts an M4A or MP3 audio file, performs speech-to-text recognition, and optionally executes the command.
    
    - **file**: M4A or MP3 audio file containing speech
    - **execute_command**: If True, parses intent and executes the command via Home Assistant
    - **min_confidence**: Minimum confidence threshold (0.0-1.0). If recognition confidence is below this, 
      the request will be rejected. Useful for noisy environments. Default: 0.7
    
    Returns:
    - **transcribed_text**: The recognized text from the audio
    - **confidence**: Confidence score of the recognition (0.0 to 1.0)
    - **intent_data**: Parsed intent information (if execute_command is True)
    - **command_result**: Result of command execution (if execute_command is True)
    """
    # Validate file type
    filename_lower = file.filename.lower() if file.filename else ""
    if not (filename_lower.endswith('.m4a') or filename_lower.endswith('.mp3')):
        raise HTTPException(
            status_code=400,
            detail="File must be an M4A or MP3 audio file"
        )
    
    # Save uploaded file temporarily
    temp_path = None
    try:
        # Determine file extension from original filename
        file_ext = '.m4a'  # default
        if filename_lower.endswith('.mp3'):
            file_ext = '.mp3'
        
        # Create temporary file with appropriate extension
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
        temp_path = temp_file.name
        temp_file.close()
        
        # Write uploaded content to temp file
        content = await file.read()
        with open(temp_path, 'wb') as f:
            f.write(content)
        
        # Perform speech recognition with confidence scores
        recognition_result = recognize_from_file(temp_path, return_confidence=True)
        transcribed_text = recognition_result.get("text", "")
        confidence = recognition_result.get("confidence", 0.0)
        
        if not transcribed_text:
            return {
                "success": False,
                "message": "No speech detected in the audio file",
                "transcribed_text": "",
                "confidence": 0.0
            }
        
        # Check confidence threshold
        if confidence < min_confidence:
            return {
                "success": False,
                "message": f"Recognition confidence ({confidence:.2f}) below minimum threshold ({min_confidence:.2f}). Audio may be too noisy or unclear.",
                "transcribed_text": transcribed_text,
                "confidence": confidence,
                "min_confidence": min_confidence
            }
        
        
        execute_command = await VoiceAssistant.search_commands(transcribed_text)
        # If we have a device command with entity_id, execute it
        if execute_command and execute_command.get("output_json", {}).get("entity_id"):
            voice_assistant_response = await VoiceAssistant.execute_command(execute_command)
            return {
                "success": voice_assistant_response["success"],
                "message": voice_assistant_response["message"],
                "response": voice_assistant_response["response"],
                "transcribed_text": transcribed_text,
                "confidence": confidence
            }

        # Check for resident location queries (e.g. "where is Reece", "where are my kids")
        location_response = await query_resident_location(transcribed_text, db)
        if location_response:
            return {
                "success": True,
                "message": "Resident location",
                "response": location_response,
                "transcribed_text": transcribed_text,
                "confidence": confidence
            }

        # Check for recent deliveries queries (e.g. "any recent deliveries", "did I get a package")
        delivery_response = await query_delivery_status(transcribed_text, db)
        if delivery_response:
            return {
                "success": True,
                "message": "Delivery status",
                "response": delivery_response,
                "transcribed_text": transcribed_text,
                "confidence": confidence
            }

        # Fall back to the LLM for other queries
        llm_response = await query_llm(transcribed_text)
        return {
            "success": True,
            "message": "Response from LLM",
            "response": llm_response,
            "transcribed_text": transcribed_text,
            "confidence": confidence
        }

    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing audio file: {str(e)}"
        )
    
    finally:
        # Clean up temporary file
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
