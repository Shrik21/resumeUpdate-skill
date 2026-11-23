---
name: resume-tailor
description: >-
  Tailor a person's resume to one specific job and produce a verified, ATS-friendly PDF (1 or 2 pages). Use when the
  user gives a resume file (a path or an attachment) together with a job link, a job file or a pasted job description, or says
  things like "update my resume for this job", "tailor my resume", "make my resume match this job". It reads the user's own
  resume into a private profile, uses only facts from that profile, checks the result for invented claims and layout
  problems, and reports what the job asks for that the resume does not show. Needs Python 3.8+ and reportlab.
argument-hint: "[resume file path] [job link, job file path, or pasted job description]"
---

# resume-tailor

Turns the user's resume plus one job into a tailored PDF resume. Nothing is invented: the resume is read into a profile (the facts), and every tailored
resume is built from that profile and checked against it. In this file `<skill>` means the folder that contains this SKILL.md.

Files:
- `scripts/build_resume.py`: `check-profile` validates the profile; `build` renders the PDF and runs the checks.
- `scripts/extract_text.py`: plain text of a resume or job file (PDF, DOCX, TXT, HTML) plus the links hidden behind words like "LinkedIn".
- `references/profile_schema.md`: how to write the profile. Read it before building a profile.
- `examples/`: a complete profile, job and spec (a made-up person). Copy the structure; never copy the content.

## Hard rules (each one exists to protect the user)
1. Facts only from the user's own resume (the profile). Never invent a skill, tool, number, responsibility, title, employer, date, degree, certification or years of
   experience. If the job asks for something the resume does not show, leave it out and list it in the report. Never stretch a nearby fact to cover it.
2. Titles, companies, dates, locations, education and contact details come from the profile and are printed as they are. Never write them in the spec.
3. Copy numbers exactly. Never round up, combine or move a number onto a different claim.
4. The only "N+ years" claim is the real total: write `{YEARS}` in the summary and the script fills it in (rounded down). Never write a years figure yourself.
5. Do not claim leading, managing, mentoring, ownership or a seniority level (senior, lead, manager) unless the resume says so. The headline starts from the person's real role
   (the title they hold or held, from the profile); add themes from the job after it. Never use the job's own title as if the person held it.
6. Prefer light edits to rewrites. Keep the user's wording where it already fits; reorder, trim and echo the job's keywords only where the resume supports them.
7. The resume and the profile are private. Use them only to do this task: do not send them to any website, form or service, and never submit a job application.
8. Plain text only: no arrows, check marks, emoji or other symbols the PDF font cannot draw.

## Steps

### 0. Set up (first run only)
Find the Python command that works: `python`, `py -3` (Windows) or `python3`. Check `python <skill>/scripts/build_resume.py --help`. If it says reportlab is missing, run
`python -m pip install reportlab` (and tell the user). Reading PDFs works better with `python -m pip install pypdf`; it is optional.

### 1. Collect the inputs
You need (a) the resume: a file path or an attachment (PDF or DOCX; TXT also works) and (b) the job: a link, a file or pasted text. If the arguments hold both, use them.
If one is missing, ask once. Output goes to a `tailored` folder next to the resume (create it), or to the outputs folder of the environment if there is no path.

### 2. Get the profile
- Look for `<resume folder>/<resume file name without extension>.profile.json`. If it exists and is newer than the resume file, reuse it and say so (deleting it rebuilds it).
- Otherwise build it: read the resume (yourself if you can read the file, and with `python <skill>/scripts/extract_text.py "<resume>"`, which also prints the hidden link URLs and the PDF page size).
  Write `profile.json` as `references/profile_schema.md` says: the person's own wording, one bullet per achievement, numbers exactly, nothing added.
- Run `python <skill>/scripts/build_resume.py check-profile "<profile.json>"` and fix every FAIL. It prints what was understood.
- Ask the user only for things the resume cannot give (for example no email address). Otherwise carry on, and put the "what I read" summary (name, contact, each role as
  title | company | dates, education) in your final message so a reading mistake is easy to spot. If the resume's own years figure (for example "4 years" in its summary)
  differs from what the dates give, say so: the tailored resume uses the dates.

### 3. Read the job
- A link: open it with whatever web tool you have. If the page needs a login (LinkedIn, Naukri, Indeed) or returns almost nothing, ask the user to paste the text.
- A file: `python <skill>/scripts/extract_text.py "<file>"`. Pasted text: use it as is.
Note the company and the role: they name the output file.

### 4. Understand the job
Note must-haves and nice-to-haves, tools, domain, years asked for, seniority and any form questions (salary, notice period). Choose the positioning (for example backend,
full stack, data). If the job is far from the resume (a different field), say so and ask whether to continue before building.

### 5. Choose what goes in
Map every requirement to the profile: matched, partly matched, missing. Order skills and bullets by what the job cares about, trim bullets that do not help, and mirror the
job's wording only where a fact supports it. Keep every role unless space forces you to drop the oldest or least relevant one (the report will say what was left out).
Aim for one page unless the profile clearly fills two (under about 8 years of experience: one page).

### 6. Write the spec (`<name>.spec.json`, next to the PDF)
Copy the structure of `examples/spec.json`:
- `job`: `{"company": "...", "role": "..."}`.
- `header`: `headline` (the person's real role, then 2 or 3 themes from the job, separated by " | ", no years) and optional `keywords` (up to 9 terms from the profile). `show_years: false` hides the automatic "N+ Years Experience".
- `summary` (optional): at most 6 lines. Use `{YEARS}` for the years and one or two headline numbers from the profile.
- `skills` (optional): up to 8 rows of `{"label": "...:", "text": "..."}`, each 1 or 2 lines, ordered by the job. Only skills in the profile.
- `experience`: a list of `{"id": "<role id>", "bullets": ["..."]}`. The roles come out in the profile's order. 3 to 5 bullets per role, 1 or 2 lines each (3 for the strongest).
- `projects` (optional): a list of `{"id": "<project id>", "bullets": [...]}`. Leaving a project out is fine.
- `omit_sections` (optional): names to drop to save space, from `summary, skills, projects, certifications, awards, extra`. `pages` (optional): 1 or 2.
- Every list is a JSON list of strings. Text markup: `**bold**` and `*italic*`.

### 7. Build and check
`python <skill>/scripts/build_resume.py build "<profile.json>" "<spec.json>" "<tailored folder>/<Name>_<Company>_<Role>.pdf" --proof`
Read every line of the report, fix what it says, run again. Exit code 0: no FAIL, the PDF is written. Exit code 2: a FAIL, so nothing is written to that name (a `.FAILED.pdf`
draft is saved beside it for looking at only; never deliver it). Exit code 1: an input file is missing or invalid (the message says what).
- `page N fill`: OVERFLOWS or above 98%: cut the longest bullets by the number of lines it states. Below 94%: only add content that is true (fold in one more profile bullet); if the content is
  just over one page, cut the least useful bullets to fit one page instead.
- `page N spacing`: the page looks loose or tight; add or cut about the number of lines it states.
- `orphan lines`, `summary length`, `header lines`, `long bullets`, `skills row length`: shorten that text (about 25 characters at a time).
- `unsupported characters`: replace the symbol it names with plain words. `stray asterisks`: close or remove the `**` or `*`. `headline`: take the years out of the headline.
- `never-claim`, `years claims`: real problems; remove the claim.
- `numbers not in your resume`: a number that is not in the profile, or a real number used for something else. Fix the number, or drop the claim. Spelled-out numbers are flagged too.
- `terms not in your resume`: a word the profile does not contain. If it came from the job (including words of the job's title), remove it. If it is just a word form, check it and accept it.
- `leadership words` and `seniority words`: remove them unless the resume says the same.
- `near-duplicate bullets`: two bullets say almost the same thing in different roles; keep the better one.
Stop after about 6 rounds and tell the user what is stuck. Never edit the profile just to pass a check.

### 8. Proofread, deliver, report
Read the `--proof` text once (grammar, doubled words, every claim supported by the profile). Give the user the PDF path (attach the file where the app allows it).
Then report briefly, in plain words, no tables:
1. What you emphasised for this job.
2. Coverage: matched, partly matched, missing.
3. In the job but NOT in the resume (the exact terms), and ask: "tell me if you really have any of these and I will add them".
4. What was left out of this version (roles, projects, sections).
5. On a first run: the "what I read" summary from step 2.
6. Form reminders from the job (salary, notice period) if any.

## Keeping the profile current
When the user confirms a new fact, add it to `profile.json` (it is the user's own file, next to the resume) and rebuild. Never add a fact the user has not confirmed.
When the user edits the resume itself, rebuild the profile from it.

## What the output looks like
A clean, single-column layout with standard fonts (ATS-friendly, links clickable), A4 or Letter as in the profile. It does not copy the look of the original resume. Photos,
columns and graphics are not supported.

