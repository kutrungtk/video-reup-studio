# Tasks

## Phase 1 — Core (DONE)
- [x] Project scaffold (PySide6)
- [x] Dark theme QSS
- [x] MainWindow + Sidebar navigation
- [x] SourcePage (1-click auto + manual)
- [x] ScriptPage (SRT load + AI rewrite)
- [x] VoicePage (TTS per segment)
- [x] ComposePage (cut + merge + subtitle)
- [x] TimelinePage (3 tracks + toolbar)
- [x] ExportPage (anti-reup + split)
- [x] SettingsPage (LLM, TTS, paths)
- [x] PipelineWorker (QThread, cancel/pause)
- [x] Copy engine modules from v2

## Phase 2 — Integration
- [ ] Wire SourcePage → PipelineWorker → real execution
- [ ] Wire ScriptPage → translator worker
- [ ] Wire VoicePage → TTS worker
- [ ] Wire ComposePage → compose worker
- [ ] Wire ExportPage → anti-reup + split worker
- [ ] Timeline auto-populate after pipeline
- [ ] Preview video playback

## Phase 3 — Polish
- [ ] Batch mode (multiple URLs)
- [ ] LLM fallback chain
- [ ] Pipeline caching (resume)
- [ ] Scene detection (keyframes)
- [ ] Content sanitization
- [ ] PyInstaller packaging → EXE
