---
name: vibecoding-workflow
description: Use ONLY when the user is starting a new vibe coding project, resuming an ongoing one, or asking how to manage long-running AI-assisted development sessions. This skill initializes and maintains a document-driven development workflow using AGENTS.md + devdocs/ to preserve context across sessions. Do not use for one-off coding tasks or simple questions.
---

# Vibe Coding Workflow

This skill manages long-running, AI-assisted development projects using a document-driven approach. AI's session memory is temporary and degrades after ~60% context usage. The solution is to persist all critical state to disk so any new session can pick up exactly where the last one left off.

## When to activate

- User says "开一个新项目" / "new project" / "init vibecoding"
- User says "继续上次的项目" / "resume" / "接着做"
- User asks about managing long-running AI coding sessions
- User's context usage exceeds 60%

## Phase 1: Project Initialization (New Project)

When the user wants to start a new vibe coding project:

### Step 1: Gather project info

Ask the user for:
1. **Project name** (e.g., "kitchen-manager")
2. **Tech stack** (e.g., "Android Kotlin + Room + Retrofit")
3. **One-sentence goal** (e.g., "A kitchen inventory app with voice input and AI recipe generation")
4. **Build command** (e.g., `./gradlew assembleDebug`)
5. **Test command** (e.g., `./gradlew test`)

If the user doesn't know some of these, make reasonable assumptions based on the tech stack and confirm with them.

### Step 2: Create the devdocs structure

Create the following files in the project root:

```
<project-root>/
├── AGENTS.md                  ← OpenCode auto-reads this every session
├── devdocs/
│   ├── plan.md                ← Overall plan with phases
│   ├── progress.md            ← Current status (what's done, what's next)
│   ├── decisions.md           ← Key technical decisions and why
│   └── archive/               ← Completed phase summaries
└── ...
```

### Step 3: Write AGENTS.md

Generate an `AGENTS.md` file tailored to the project. It must include:

```markdown
# <Project Name>

## Build
<build command>

## Test
<test command>

## Project Structure
<brief directory layout>

## Tech Stack
<list of frameworks/libraries>

## Development Rules
- <coding style rules>
- Before starting any work, read devdocs/progress.md
- After completing any milestone, update devdocs/progress.md
- When context usage exceeds 60%, proactively update progress.md and suggest starting a new session

## Current Phase
See devdocs/progress.md for current status.
```

### Step 4: Write plan.md

Break the project into 3-5 phases. Each phase should be completable in 1-2 sessions:

```markdown
# Development Plan

## Phase 1: Core Foundation
- [ ] Project scaffolding and basic UI
- [ ] Database setup (Room)
- [ ] Basic CRUD for inventory

## Phase 2: AI Integration
- [ ] LLM API integration
- [ ] Voice input -> structured data pipeline
- [ ] Recipe generation from inventory

## Phase 3: Polish & Ship
- [ ] Error handling and edge cases
- [ ] UI polish
- [ ] Build release APK
```

### Step 5: Write progress.md

```markdown
# Current Progress

## Status: Phase 1 - Not Started
## Last Updated: <date>
## Last Session Summary: N/A

## Completed
(none yet)

## In Progress
(none yet)

## Next Steps
1. <first task from plan.md>

## Known Issues
(none yet)

## Notes for Next Session
(none yet)
```

### Step 6: Write decisions.md

```markdown
# Technical Decisions

| Date | Decision | Reason |
|------|----------|--------|
| <today> | <tech stack choice> | <why> |
```

### Step 7: Confirm with user

Show the user the generated file structure and contents. Ask if they want to adjust anything before starting work.

## Phase 2: Working Session (Active Development)

When a session is actively developing code:

### Context monitoring

Continuously monitor context usage. At key thresholds:

- **50%**: Remind the user that context is getting heavy. Suggest focusing on the current task.
- **60%**: Proactively update `devdocs/progress.md` with current state. Tell the user: "Context is at 60%. I've saved progress. We can continue but consider wrapping up the current task soon."
- **70%**: Strongly recommend ending the session. Update all devdocs files. Tell the user: "Context is at 70%. I strongly recommend we save progress and start a fresh session. Quality will degrade if we continue."

### After completing a task

After each meaningful milestone (a feature, a bug fix, a refactor):

1. Update `devdocs/progress.md`:
   - Move completed items from "In Progress" to "Completed"
   - Update "Next Steps"
   - Update "Last Updated" timestamp
2. If a significant technical decision was made, add it to `devdocs/decisions.md`.
3. Commit the code changes with a descriptive message.

### End of session protocol

When ending a session (user says "先到这" / "save and quit" / context is high):

1. Update `devdocs/progress.md` with:
   - Everything completed this session
   - What was in the middle of being done
   - Specific next steps (be very detailed, not vague)
   - Any gotchas or things the next session needs to know
2. Update `devdocs/decisions.md` if any new decisions were made.
3. Commit all changes.
4. Tell the user: "Progress saved. To continue next time, open a new session and say '继续项目' or 'resume'."

## Phase 3: Session Resume

When the user says "继续" / "resume" / "接着做" / "继续上次的":

### Step 1: Read devdocs

Read these files in order:
1. `AGENTS.md` (project overview)
2. `devdocs/progress.md` (where we left off)
3. `devdocs/plan.md` (overall roadmap)
4. `devdocs/decisions.md` (past decisions to respect)

### Step 2: Summarize status to user

Present a brief status report:
```
Project: <name>
Current Phase: <phase N>
Last Session: <date>
Completed: <X of Y tasks>
Next Up: <specific next task>
```

### Step 3: Confirm and continue

Ask: "Ready to continue with <next task>? Or do you want to adjust the plan?"

Then proceed with development.

## Phase 4: Phase Completion

When all tasks in a phase are done:

1. Create `devdocs/archive/phase-N.md` with:
   - What was built
   - Key decisions made
   - Lessons learned
   - Approximate token/cost spent (if known)
2. Update `devdocs/plan.md`: mark phase as complete.
3. Update `devdocs/progress.md`: reset "In Progress" and "Completed" sections, set "Next Steps" to phase N+1 tasks.
4. Celebrate with the user.

## Anti-patterns

- Do NOT rely on session memory for anything critical. Always write to files.
- Do NOT let context exceed 75% without having updated progress.md.
- Do NOT start a new session without reading devdocs/ first.
- Do NOT write vague progress notes like "made some progress on the UI". Be specific: "Completed RecyclerView adapter for inventory list, added swipe-to-delete, pending: empty state view."
- Do NOT skip the end-of-session protocol. Even if the user just says "bye", update progress.md before closing.
