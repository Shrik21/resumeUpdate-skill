# resume-tailor

Give it your resume and a job. It hands back a resume tailored to that job as a clean PDF, using only things your resume already says.

## What you need
- Claude Code (desktop app or terminal) or Claude with skills turned on
- Python 3.8 or newer, and one library: `python -m pip install reportlab` (Claude will offer to do this for you the first time)

## Install
- Claude Code: copy the whole `resume-tailor` folder into your skills folder.
  - Windows: `C:\Users\<your name>\.claude\skills\resume-tailor`
  - macOS / Linux: `~/.claude/skills/resume-tailor`
  Start a new Claude Code session afterwards.
- Claude.ai: Settings -> Capabilities -> Skills -> upload the zip.

## Use
Say it in plain words or use the command, with the path of your resume and the job link (or paste the job description):

```
/resume-tailor C:\Users\me\Documents\MyResume.pdf https://company.com/careers/backend-engineer
```

or: "Update my resume at C:\Users\me\Documents\MyResume.pdf for this job: <paste the job description>".

The first time, Claude reads your resume and saves your facts next to it as `MyResume.profile.json`. It shows you what it understood (your roles, dates and
education): check that list, because everything is built from it. Later runs reuse the saved file, so you only give the new job.
The tailored PDF and a small `.spec.json` file are saved in a `tailored` folder next to your resume.

## What it will not do
- It will not invent anything: no new skills, numbers, titles, dates or years. If the job asks for something your resume does not show, it tells you
  instead of adding it. If you really have that skill, tell it and it will add it to your profile.
- It will not claim leading, managing or a senior level that your resume does not say.
- It will not apply for the job. You send the PDF yourself.

## Good to know
- The output uses one fixed clean layout (single column, standard fonts), not the design of your original resume. No photos or graphics.
- It fits one page when it can and two when the content needs them. If the last page would be mostly empty, it says so instead of padding.
- Your resume and the saved profile are files on your computer, and the skill sends them nowhere else (Claude reads them to do the work, as with any file you share with it). The skill folder itself contains no personal data.
- Text must use normal Latin letters and punctuation. Arrows, check marks and emoji are replaced with words.

