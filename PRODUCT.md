# Product

## Register

product

## Users

Two audiences arrive at the same page with different jobs.

**The n8n builder.** A freelancer, agency operator, or ops person who built a
workflow in the n8n UI and is about to send the exported JSON somewhere it cannot
be recalled: a client, a public repo, a template marketplace. They are mildly
anxious and asking one question: *did I leave a key in this?* They mostly do not
write code, have never opened a terminal, and will not install Python to find
out. They want an answer they can trust and act on within a minute.

**The evaluator.** Someone assessing the person who built the tool, arriving from
a CV or a profile link with about thirty seconds of attention and no n8n workflow
of their own. They are not here to lint anything. They are deciding whether the
work is real.

The page has to satisfy the first without pandering to the second.

## Product Purpose

Reads an exported n8n workflow and answers whether it is safe to share, whether
it will fail silently in production, and what it costs to run. Seventeen rules
across three categories: leaked credentials, reliability gaps, and cost.

Success is a builder who catches a live API key before pushing it to a public
repo, and understands the fix without knowing what JSON is.

The whole analysis runs inside the browser tab. Nothing is uploaded, because a
tool for finding embedded credentials should not ask you to send the file
containing them to somebody else's server.

## Brand Personality

**Official, plain-spoken, unflinching.**

The reference object is an inspection certificate or a lab result: a document
that states a finding, signs its work, and does not editorialise. Authority comes
from structure, precision, and the willingness to be checked, not from visual
confidence.

Voice is plain and specific. It explains what a finding means to somebody who has
never heard the word "credential", and it names the exact steps in n8n that fix
it. It never hedges a real problem and never inflates a small one.

The tool documents where it might be wrong: its false-positive rates are
published, one of its own rules was demoted for firing too often, and its price
table prints the date it was last checked.

## Anti-references

- **Playful or cute.** No illustrations, mascots, rounded friendly type, or emoji
  as interface. A security finding delivered warmly reads as unserious.
- **Hacker terminal.** Black background, neon-green monospace, padlock and shield
  icons. The first cliche any security tool falls into.
- **Generic SaaS.** Uniform rounded card grid, soft drop shadows, gradient blob,
  friendly blue. The default template look.
- **Corporate security vendor.** Navy and teal, abstract network graphics, trust
  badges, compliance language nobody reads.
- **Alarm theatre.** Sirens, pulsing red, scare copy. The finding is serious
  enough on its own; dramatising it makes the tool look like it is selling
  something.

## Design Principles

**Verdict before detail.** The first question is always "is this safe to send?"
That answer appears before any finding, in language requiring no expertise. Every
other element is subordinate to it.

**Practice what the tool preaches.** The page audits others for hidden costs and
quiet failures, so it cannot have any. No uploads, no analytics, no tracking, no
webfont phoning home. The privacy claim is stated and then made checkable in the
browser's own Network tab.

**Plain language is the product, not a mode.** The explanations are the reason
the page exists. Technical output is available for people who want it, but it is
the secondary view.

**Severity is information, not decoration.** Colour appears only where it
distinguishes an exposed credential from a naming nit. Nothing is tinted for
atmosphere.

**Show the working.** Cost estimates print their assumptions. Prices print their
verification date. Findings name the exact step. A number nobody can check is a
number nobody should trust.

## Accessibility & Inclusion

- WCAG 2.2 AA. Body text at least 4.5:1, large text at least 3:1, verified rather
  than assumed.
- Severity is never carried by colour alone. Every finding is also marked by a
  word, its position in the ordered schedule, and its typographic weight, so the
  report is readable in greyscale and to colour-blind users.
- Full keyboard operation, including the drop zone. Visible focus throughout.
- Results announced to assistive technology when a scan completes.
- `prefers-reduced-motion` honoured: transitions become instant, no exceptions.
- Readable at 320px and at 200% zoom without horizontal scrolling.
