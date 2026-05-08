Mutt TTS Generator v1.0.0.4
=============================

Portable TTS (Text-to-Speech) generator with multi-backend support.

SETUP:
1. Copy MuttTTS.exe to any folder
2. Create .env file in the SAME folder as MuttTTS.exe
3. Add your API keys to .env:

   MIMO_API_KEY=your_mimo_key
   OPENROUTER_API_KEY=your_openrouter_key
   GROQ_API_KEY=your_groq_key
   OPENAI_API_KEY=your_openai_key
   ELEVENLABS_API_KEY=your_elevenlabs_key
   MISTRAL_API_KEY=your_mistral_key

   (Get keys from the links shown in the app)

4. Run MuttTTS.exe

NOTE: ElevenLabs is geo-blocked in Russia (returns 302 redirect).
      Use VPN or choose a different backend in the app.

Backends:
- MiMo (free, Chinese)
- OpenRouter (7 models, paid)
- Groq (Orpheus EN/AR, free tier)
- OpenAI Direct (tts-1, paid)
- ElevenLabs (8 voices, geo-blocked in RU)
- Mistral (10 preset voices, $16/1M chars)

Built with Python 3.12, ttkbootstrap, pygame.
Repo: https://github.com/nmlssfx/mutt
