# app/routes/voice.py

import os
import tempfile
from fastapi import APIRouter, Query, Depends, UploadFile, File, HTTPException
from app.voice.handler import IntentParser
from app.voice.recognizer import recognize_from_file
from app.core.homeassistant import LightControl
from app import models, auth, schemas
from app.voiceassistant.va import VoiceAssistant

router = APIRouter(prefix="/voice", tags=["Voice Assistant"])


@router.get("/command")
async def voice_command(
    text: str = Query(..., description="Command text from user"),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Accepts a voice command as text, parses intent, and executes action via Home Assistant.
    Example: /voice/command?text=turn on the guest room light
    """
    execute_command = await VoiceAssistant.search_commands(text)
    return {"success": True, "message": "Command executed", "response": execute_command}
    # if execute_command:
    #     return await VoiceAssistant.execute_command(execute_command)
    # else:
    #     return {
    #         "success": False,
    #         "message": "No command found"
    #     }


@router.post("/stt")
async def speech_to_text(
    file: UploadFile = File(..., description="MP3 audio file for speech recognition"),
    execute_command: bool = Query(False, description="Whether to execute the recognized command"),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Accepts an MP3 audio file, performs speech-to-text recognition, and optionally executes the command.
    
    - **file**: MP3 audio file containing speech
    - **execute_command**: If True, parses intent and executes the command via Home Assistant
    
    Returns:
    - **transcribed_text**: The recognized text from the audio
    - **intent_data**: Parsed intent information (if execute_command is True)
    - **command_result**: Result of command execution (if execute_command is True)
    """
    # Validate file type
    if not file.filename.lower().endswith('.mp3'):
        raise HTTPException(
            status_code=400,
            detail="File must be an MP3 audio file"
        )
    
    # Save uploaded file temporarily
    temp_path = None
    try:
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        temp_path = temp_file.name
        temp_file.close()
        
        # Write uploaded content to temp file
        content = await file.read()
        with open(temp_path, 'wb') as f:
            f.write(content)
        
        # Perform speech recognition
        transcribed_text = recognize_from_file(temp_path)
        
        if not transcribed_text:
            return {
                "success": False,
                "message": "No speech detected in the audio file",
                "transcribed_text": ""
            }
        
        # If execute_command is False, just return the transcribed text
        if not execute_command:
            return {
                "success": True,
                "transcribed_text": transcribed_text,
                "message": "Speech recognized successfully"
            }
        
        execute_command = await VoiceAssistant.search_commands(transcribed_text)
        if execute_command:
            voice_assistant_response = await VoiceAssistant.execute_command(execute_command)
            return {
                "success": voice_assistant_response["success"],
                "message": voice_assistant_response["message"],
                "response": voice_assistant_response["response"],
                "transcribed_text": transcribed_text
            }
        else:
            return {
                "success": False,
                "message": "No command found",
                "transcribed_text": transcribed_text
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
