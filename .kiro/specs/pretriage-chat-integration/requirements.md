# Requirements Document

## Introduction

This feature connects the existing Non-Emergency Consultation page (`frontend/chat.html`) to the live Project ARIA triage backend (`non-emergency-pretriage/chat_functionality.py`). Today all three input modes on the page (Text, Image, Voice) return hard-coded, simulated responses via `setTimeout`. This feature replaces those placeholders with real calls to the backend HTTP API so a patient can hold a multi-turn triage conversation, upload a photo of a wound or rash for visual assessment, and speak in their own language and hear ARIA reply.

The backend already exposes the conversational logic, translation, image analysis, red-flag emergency detection, clinic routing, and Amazon Polly speech synthesis. The scope of this feature is the frontend integration: issuing the correct HTTP requests, preserving conversation session continuity, uploading media to S3 via presigned URLs, rendering real replies, playing back returned audio, surfacing escalation and clinic-routing outcomes, and handling errors and loading states. No backend behavior is changed by this feature.

## Glossary

- **Chat_Client**: The browser-side JavaScript contained in `frontend/chat.html` that drives the Non-Emergency Consultation page.
- **Triage_API**: The backend HTTP API served by the `lambda_handler` in `chat_functionality.py`.
- **Chat_Endpoint**: The `POST /chat` route of the Triage_API. Accepts `{ message, session_id?, image_key?, audio_key?, speak?, lat?, lng?, phone? }` and returns `{ session_id, reply, reply_english, action, escalated, image_analyzed, image_findings, audio_url, patient_text, clinic, language }`.
- **Upload_Endpoint**: The `POST /upload-url` route of the Triage_API. Accepts `{ type, ext }` where `type` is `"audio"` or `"image"`, and returns `{ upload_url, key }`.
- **Session_Id**: The `session_id` string returned by the Chat_Endpoint that identifies a single conversation, used to maintain multi-turn continuity.
- **Media_Key**: The S3 object key (`key`) returned by the Upload_Endpoint, passed back to the Chat_Endpoint as `image_key` or `audio_key`.
- **Presigned_Url**: The `upload_url` returned by the Upload_Endpoint that permits a direct HTTP PUT of a media file to S3.
- **Audio_Url**: The `audio_url` field returned by the Chat_Endpoint; a presigned URL to an MP3 of ARIA's spoken reply, or `null` when no audio was produced.
- **Action**: The `action` field returned by the Chat_Endpoint; one of `"continue"`, `"advise"`, or `"route_to_clinic"`.
- **Clinic_Info**: The `clinic` object returned by the Chat_Endpoint when a patient is routed; contains `name`, `location`, and `distance_km`, or `null`.
- **API_Config**: The configurable values the Chat_Client uses to reach the Triage_API, comprising the base URL and Cognito authentication settings.
- **Cognito_Token**: The Cognito-issued JSON Web Token (JWT) identifying the signed-in patient, which the Chat_Client sends to authenticate Triage_API requests.

## Requirements

### Requirement 1: API Configuration

**User Story:** As a developer deploying the page, I want the backend location and Cognito settings defined in one place, so that I can point the page at the deployed Triage_API without editing logic.

#### Acceptance Criteria

1. THE Chat_Client SHALL read the Triage_API base URL from a single named configuration value defined at the top of the script.
2. WHEN the Chat_Client sends a request to the Triage_API, THE Chat_Client SHALL prepend the configured base URL to the route path.
3. WHEN the patient has a valid Cognito_Token, THE Chat_Client SHALL include the Cognito_Token in the `Authorization` request header as a bearer token.
4. IF the patient has no valid Cognito_Token, THEN THE Chat_Client SHALL prompt the patient to sign in and SHALL NOT send the request to the Triage_API.

### Requirement 2: Text Chat Turn

**User Story:** As a patient, I want to type my symptoms and get a real reply from ARIA, so that I receive guidance about my condition.

#### Acceptance Criteria

1. WHEN the patient submits non-empty text, THE Chat_Client SHALL display the submitted text as a patient message in the conversation.
2. WHEN the patient submits non-empty text, THE Chat_Client SHALL send a `POST` request to the Chat_Endpoint with a body containing the `message` field set to the submitted text.
3. WHILE a Session_Id is held from a prior turn, THE Chat_Client SHALL include that Session_Id as the `session_id` field in the Chat_Endpoint request.
4. WHEN the Chat_Endpoint returns a successful response, THE Chat_Client SHALL display the `reply` field as an ARIA message in the conversation.
5. IF the patient submits empty or whitespace-only text, THEN THE Chat_Client SHALL take no action and SHALL NOT send a request to the Chat_Endpoint.

### Requirement 3: Session Continuity

**User Story:** As a patient, I want ARIA to remember what I said earlier in the conversation, so that I do not have to repeat myself across turns.

#### Acceptance Criteria

1. WHEN the Chat_Endpoint returns a `session_id` and the Chat_Client holds no Session_Id, THE Chat_Client SHALL store the returned `session_id` as the Session_Id.
2. IF storing the returned `session_id` fails, THEN THE Chat_Client SHALL display an error message and SHALL treat the turn as failed.
3. WHERE a Session_Id is already held, THE Chat_Client SHALL include the held Session_Id on every subsequent Chat_Endpoint request regardless of input mode.
4. WHEN the patient sends a turn through any input mode, THE Chat_Client SHALL reuse the single held Session_Id rather than starting a separate conversation per mode.

### Requirement 4: Image Upload and Analysis

**User Story:** As a patient, I want to upload a photo of a wound or rash and have ARIA assess it, so that I get guidance based on what the photo shows.

#### Acceptance Criteria

1. WHEN the patient confirms an image for analysis, THE Chat_Client SHALL send a `POST` request to the Upload_Endpoint with `type` set to `"image"` and `ext` set to the file extension of the selected image.
2. WHEN the Upload_Endpoint returns a Presigned_Url and a Media_Key, THE Chat_Client SHALL upload the selected image file to the Presigned_Url using an HTTP `PUT` request.
3. WHEN the image upload to the Presigned_Url succeeds, THE Chat_Client SHALL send a `POST` request to the Chat_Endpoint with the `image_key` field set to the returned Media_Key.
4. IF the image upload to the Presigned_Url does not succeed, THEN THE Chat_Client SHALL NOT send the image turn to the Chat_Endpoint.
5. WHEN the patient confirms an image for analysis, THE Chat_Client SHALL display the selected image as a patient message in the conversation.
6. WHEN the Chat_Endpoint returns a successful response for an image turn, THE Chat_Client SHALL display the `reply` field as an ARIA message in the conversation.
7. IF the patient confirms analysis with no image selected, THEN THE Chat_Client SHALL take no action and SHALL NOT send a request to the Upload_Endpoint.

### Requirement 5: Voice Capture and Upload

**User Story:** As a patient, I want to speak my symptoms in my own language, so that I can use the service without typing.

#### Acceptance Criteria

1. WHEN the patient activates the microphone control, THE Chat_Client SHALL request microphone access and begin recording audio.
2. WHEN the patient releases the microphone control after recording, THE Chat_Client SHALL stop recording and produce a single audio file.
3. WHEN recording stops, THE Chat_Client SHALL send a `POST` request to the Upload_Endpoint with `type` set to `"audio"` and `ext` set to the recorded audio file extension.
4. WHEN the Upload_Endpoint returns a Presigned_Url and a Media_Key for audio, THE Chat_Client SHALL upload the recorded audio file to the Presigned_Url using an HTTP `PUT` request.
5. WHEN the audio upload to the Presigned_Url succeeds, THE Chat_Client SHALL send a `POST` request to the Chat_Endpoint with the `audio_key` field set to the returned Media_Key and the `speak` field set to `true`.
6. WHEN the Chat_Endpoint returns a `patient_text` value for a voice turn, THE Chat_Client SHALL display the `patient_text` value as a patient message in the conversation.
7. IF microphone access is denied, THEN THE Chat_Client SHALL display a message informing the patient that microphone access is required.

### Requirement 6: Spoken Reply Playback

**User Story:** As a patient who prefers listening, I want to hear ARIA's reply aloud, so that I can understand the guidance without reading.

#### Acceptance Criteria

1. WHEN the Chat_Endpoint returns a non-null Audio_Url, THE Chat_Client SHALL play the audio located at the Audio_Url.
2. IF the Chat_Endpoint returns a null Audio_Url, THEN THE Chat_Client SHALL display the text reply without attempting audio playback.
3. IF audio playback fails, THEN THE Chat_Client SHALL display the text reply and SHALL continue accepting further patient input.

### Requirement 7: Escalation and Clinic Routing Display

**User Story:** As a patient with a serious condition, I want to be clearly told when I should go to a clinic and which clinic to visit, so that I can get in-person care.

#### Acceptance Criteria

1. WHEN the Chat_Endpoint returns `escalated` as `true`, THE Chat_Client SHALL display a visually distinct notice indicating that the patient is being routed to in-person care.
2. WHEN the Chat_Endpoint returns a non-null Clinic_Info, THE Chat_Client SHALL display the clinic `name`, `location`, and `distance_km` from the Clinic_Info.
3. WHILE the Action is `"route_to_clinic"`, THE Chat_Client SHALL display the `reply` field text in the conversation.

### Requirement 8: Patient Location for Clinic Routing

**User Story:** As a patient who may need a clinic, I want the nearest clinic to be found from my location, so that I am directed somewhere I can reach.

#### Acceptance Criteria

1. WHEN the consultation begins, THE Chat_Client SHALL request the patient's geographic location from the browser.
2. WHERE the patient grants location access AND both latitude and longitude are available, THE Chat_Client SHALL include the latitude as `lat` and the longitude as `lng` in Chat_Endpoint requests.
3. IF the patient denies location access, THEN THE Chat_Client SHALL send Chat_Endpoint requests without the `lat` and `lng` fields.
4. IF only one of latitude or longitude is available, THEN THE Chat_Client SHALL send Chat_Endpoint requests without the `lat` and `lng` fields.

### Requirement 9: Request Failure Handling

**User Story:** As a patient, I want to be told when something goes wrong with my request, so that I know to try again rather than waiting indefinitely.

#### Acceptance Criteria

1. IF a request to the Chat_Endpoint returns a non-success HTTP status, THEN THE Chat_Client SHALL display an error message in the conversation.
2. IF a request to the Upload_Endpoint returns a non-success HTTP status, THEN THE Chat_Client SHALL display an error message in the conversation.
3. IF an upload to a Presigned_Url returns a non-success HTTP status, THEN THE Chat_Client SHALL display an error message in the conversation.
4. IF a network error prevents a request from completing, THEN THE Chat_Client SHALL display an error message in the conversation.
5. WHEN an error message is displayed, THE Chat_Client SHALL restore the input controls so the patient can attempt another turn, such that an error message is shown only together with restored input controls.

### Requirement 10: Processing State Feedback

**User Story:** As a patient, I want to see that ARIA is working on my message, so that I know my input was received.

#### Acceptance Criteria

1. WHEN the Chat_Client sends a turn to the Chat_Endpoint, THE Chat_Client SHALL display a processing indicator until a response is received or the request fails.
2. WHEN a Chat_Endpoint response is received, THE Chat_Client SHALL remove the processing indicator.
3. WHILE a turn is being processed, THE Chat_Client SHALL prevent submission of an additional concurrent turn.
