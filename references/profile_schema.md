# The profile: the person's facts

The profile is a JSON file with the facts from the person's own resume, and nothing else. Every tailored resume is built from it, and the checks
flag anything on the page that the profile does not contain. Keep it next to the resume as `<resume name>.profile.json`.

Build it by copying, not by improving: use the person's own wording, one bullet per achievement, numbers and units exactly as written.
Anything the resume does not say stays out. If something is missing (no phone, unclear dates), ask the user.

## Fields

| Key | Required | What goes in it |
|---|---|---|
| `name` | yes | Full name as on the resume. |
| `contact` | yes | `{"phone": "...", "email": "...", "location": "City, Country"}`. `email` is required; `phone` and `location` are optional but recruiters expect a phone. |
| `links` | no | `{"LinkedIn": "https://...", "GitHub": "https://..."}`. Label -> full URL (http or https). The label is shown as a word and carries the link. Take the URLs from the "links found in the file" list that `extract_text.py` prints, because a resume often hides the URL behind the word. |
| `career_start` | if there is experience | Year-month of the first job, like `2019-06`. It drives the `{YEARS}` placeholder and the years check. Do not count education or internships unless the resume counts them. |
| `page_size` | no | `A4` (default) or `Letter`. Use what the original resume uses (`extract_text.py` prints it for PDFs). |
| `headline` | no | The title line of the original resume, if it has one. It is a fact source, not a rendered field. |
| `summary` | no | The original resume's summary text, if it has one. A fact source: the tailored summary can reuse its claims. |
| `experience` | no | List of roles, newest first (see below). |
| `projects` | no | List of projects (see below). |
| `education` | no | List of entries (see below). |
| `skills` | no | List of `{"label": "Languages:", "text": "Python, Java"}` rows, as the resume groups them. If the resume has one flat list, group it into 3 to 6 rows without adding skills. |
| `certifications` | no | List of one-line strings, for example `"AWS Certified Cloud Practitioner (2022)"`. |
| `awards` | no | List of one-line strings. |
| `extra_sections` | no | `[{"title": "Volunteering", "bullets": ["..."]}]` for anything else the resume has (publications, languages, volunteering). Printed as written. |
| `section_order` | no | Order of sections, a subset of `summary, skills, experience, projects, education, certifications, awards, extra`. Freshers often put `education` first. |
| `section_titles` | no | Rename headings, for example `{"skills": "TECHNICAL SKILLS", "experience": "WORK EXPERIENCE"}`. |
| `show_years` | no | `false` hides the automatic "N+ Years Experience" in the headline (use it for freshers). |
| `known_terms` | no | Extra capitalised words the checks should accept (product names that are not in the resume, for example). Rarely needed. |
| `never_claim` | no | Terms that must never appear on this person's resumes. A leading `=` makes a term case-sensitive. Add what the user says they do not want to claim. |
| `notes` | no | Free text for the next run (for example "user is not sure about Docker"). Not printed and not a fact source. |

### experience

```json
{"id": "orbit", "title": "Senior Software Engineer", "company": "Orbit Labs", "location": "Pune, India",
 "dates": "Jan 2023 - Present", "bullets": ["Built REST APIs in Python serving 1.2M requests per day", "..."]}
```
`id` is a short key (letters, digits, `-`, `_`) used by the job spec. `title`, `company`, `dates` are copied exactly from the resume. `location` is optional.
Put every bullet of the role here, even the ones that will not suit most jobs: the profile is the full list of facts, and each job picks from it.
Two jobs at one company are two roles.

### projects

```json
{"id": "stockpilot", "name": "Stockpilot", "descriptor": "Inventory forecasting service", "context": "Orbit Labs",
 "dates": "2024", "bullets": ["..."]}
```
Only `id`, `name` and `bullets` are required. `context` is the employer or "Personal project".

### education

```json
{"institution": "Example Institute of Technology", "degree": "Bachelor of Technology (B.Tech), Computer Science",
 "dates": "Jun 2018", "place": "Pune, India", "details": "CGPA: 8.1"}
```
Only `institution` and `degree` are required. Never state a degree branch, grade or date the resume does not show.

## Rules while reading the resume

1. One fact per bullet. Split a paragraph into bullets at the sentence level; do not merge or shorten.
2. Keep numbers exactly (`40%`, `1.2M`, `15k`), including words like "over" or "about".
3. Keep the user's tool names as written (`Node.js`, `PostgreSQL`). Do not "normalise" or add related tools.
4. Do not turn a skill list into claims about achievements, and do not add skills that only appear in the job.
5. Text must use characters the PDF font can draw (Latin letters, normal punctuation). Replace arrows, check marks and emoji with words; spell a name with
   letters outside Western European alphabets in the closest Latin letters and tell the user.
6. After writing it, run `python <skill>/scripts/build_resume.py check-profile profile.json` and fix every FAIL.

