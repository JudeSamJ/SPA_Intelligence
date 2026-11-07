# SPA Intelligence: the business problem, the solution and the logic behind it

Audience: a manager or client who wants to understand *why* this product exists and *how* it decides things.
Status: describes what is built today and what the Supabase step adds. Statements about law are illustrative and
**not lawyer-reviewed** (the rule packs are marked that way in the product).

---

## 1. The problem

A property buyer signs a **Sale and Purchase Agreement (SPA)**. It is a long legal PDF, often 30 to 80 pages. The
buyer then waits months or years for the property to be finished. During that time they need to know things like:

- When is my handover date, and how much grace does the seller get?
- If the seller is late, how much compensation do I get, and is it capped?
- Which payments do I owe, when, and what triggers them?
- Which deadlines do I have to meet (inspection, defect notices, cancellation rights)?

Today these answers are buried in dense clauses. The people who need them fall into three groups:

| Who | What goes wrong today |
|---|---|
| **Buyers** | They cannot read the SPA. They ask the sales team the same questions, or guess, or miss a deadline. |
| **Developer staff and reviewers** | They read each contract by hand, copy figures into a spreadsheet, and make arithmetic mistakes. |
| **Legal and finance teams** | Questions arrive that only they can answer, so they become a bottleneck. They have no quick way to check a contract against the statute. |

The costly failures are specific: **a wrong delay-compensation figure, a missed notice deadline, or a confident wrong
answer to a buyer**. Each one creates disputes, refunds, regulator complaints or lost trust.

## 2. What we are solving, and what we are not

**We solve:** turning one SPA PDF into checked, structured, explainable facts, then using those facts to calculate
exposure, track deadlines and answer buyer questions, with a person still in control of anything uncertain.

**We do not solve, and the product says so:**

- Legal advice. Every output carries "Decision support, not legal advice."
- Deciding disputes, cancellations or refunds. Those questions are refused and sent to the legal team.
- Reading contracts that are not property sale agreements.

## 3. The approach, and why we chose it

A plain "ask an AI about the contract" tool fails this use case, because a language model can invent a number that
looks right. So the design follows five rules.

| Rule | What it means | Why |
|---|---|---|
| **The model only reads. Code calculates.** | The language model extracts text and values. All arithmetic (delay interest, cap, cash flow, statute gap) runs in tested Python. | Money must not depend on a model's guess. |
| **Source or nothing.** | Every value has a page number and an exact quote. If the contract does not say it, the product shows "not stated". | Every figure can be checked in seconds. |
| **Prove it before trusting it.** | After extraction, code finds each quote on the PDF page and marks the value grounded, partial, ungrounded or not stated. | Catches the model's mistakes automatically. |
| **People decide the uncertain.** | Weak or flagged values go to a review queue where a reviewer accepts, corrects or rejects them. | Responsibility stays with a human. |
| **Refuse what it should not answer.** | Legal-advice questions and questions about other buyers are refused before any model call. | A wrong answer here is worse than no answer. |

## 4. The workflow end to end

```
1  UPLOAD      Staff uploads the SPA PDF.
2  EXTRACT     The model reads the text and returns terms: buyer, unit, price, area,
               handover date, grace period, delay rate, cap, payment plan, clauses.
3  GROUND      Code locates every quote on its page, highlights it, and assigns a status.
4  REVIEW      Anything weak goes to the review queue. A reviewer accepts, corrects or rejects.
5  CALCULATE   Python computes delay compensation, cash flow, exposure ranges, and compares
               the terms with the jurisdiction rule pack (statute gap).
6  WATCH       Dated clauses become obligations with due dates. A daily check raises alerts.
7  NOTIFY      Alerts and "contract ready" events go out by email (designed, with a summary card).
8  ANSWER      The buyer asks questions. The assistant answers only from that buyer's contract,
               with page and quote, and refuses legal or cross-buyer questions.
9  IMPROVE     Reviewer corrections feed an accuracy set, so quality is measured, not claimed.
```

Who does what:

| Role | Can do |
|---|---|
| **Staff** | Upload, view terms, calculations, obligations. |
| **Reviewer** | Everything staff can, plus verify or correct values and send test alerts. |
| **Buyer** | Ask questions about their own contract only. |

## 5. The business logic, rule by rule

### 5.1 Extraction and trust
- A value is only accepted if it has a page and a non-empty quote.
- A missing value stays empty. It is never filled with a guess.
- Grounding status: **grounded** (quote found on the stated page), **partial** (close match), **ungrounded** (not found),
  **not stated** (the contract does not say it).
- Each value gets a confidence score from fixed weights in a rules file, not from the model's own claim.

### 5.2 Delay compensation
Inputs come from the contract: handover date, grace period (days), delay rate and its basis (percent per annum, or a
fixed amount per square foot per year), and the cap (percent of price).

1. Delay starts after **handover date + grace period**.
2. For each day late, compensation accrues at the contract's rate on the purchase price (or per sq ft).
3. The total stops at the **cap** if the contract has one. If the contract says there is no cap, that is shown.
4. The result is reported with the clause that produced each input.

All of this runs in Python with hand-calculated test cases. The model never computes it.

### 5.3 Payment plan and cash flow
- Milestone percentages are read as stated, then **summed**. If they do not total 100 percent, a warning appears.
- Payments are laid out by month or quarter, showing how much is tied to construction and how much to handover.

### 5.4 Obligations and alerts
- Clauses such as "within 14 days after the Notice of Completion" become obligations with an anchor event and a
  computed due date.
- A daily job checks for upcoming and overdue obligations and raises one alert per item, so nobody is spammed.

### 5.5 Statute gap
- Each jurisdiction has a rule pack (for example Dubai and India RERA) that states the statutory rule, such as a
  compensation rate or a defect-liability period.
- The product compares the contract with the pack and shows the gap with both sources.
- Every pack is marked **not reviewed by a lawyer**. A lawyer must review them before client use.

### 5.6 Buyer assistant
- The buyer's identity decides which contract is used. The chat text never chooses the contract.
- The assistant calls tools that return grounded facts and clauses, then phrases the answer.
- A guard replaces any answer that has no tool result behind it, or that contains a figure no tool returned.
- Refusals happen before any model call, so they cost nothing and cannot be talked around.
- Every question and tool call is audit-logged, without contract text.

## 6. Why a database (the Supabase step)

Today the app keeps its data in local files on the server: uploaded PDFs, extractions, review decisions, alerts and
cross-document sets. On the free hosting tier those files are **erased on every restart**. That is acceptable for a
demo and unacceptable for a product.

A real database gives us:

| Need | What we use |
|---|---|
| Data that survives restarts and redeploys | Supabase **Postgres** |
| The original PDFs and every saved result, kept safely | The same Postgres database (a durable copy of each file) |
| Many contracts, each linked to its buyer, without editing server settings | A **buyer assignment** table |
| Access that cannot leak between buyers | **Row Level Security** plus server-side checks |
| A history of who reviewed what | Review and audit tables |
| Backups and a visible admin view | Supabase dashboard |

### Planned tables

| Table | Holds |
|---|---|
| `app_files` | A durable copy of every file the app keeps: PDFs, extractions with grounding results, review decisions, alerts, document sets |
| `contracts` | One readable row per SPA: file name, pages, status, model, open review items |
| `buyer_assignments` | Which buyer identity (email or phone) may ask about which contract |
| `audit_log` | Questions and tool calls, without contract text |

### Security model
- The app server holds the Supabase **service key** as a secret environment variable. It never reaches the browser.
- Buyers never get a database login. Our API checks the buyer assignment table before answering.
- PDFs are served only through the authenticated API; the database tables are closed to Supabase's public REST API.

## 7. What is necessary, and what is optional

| Part | Necessary for the product? | Reason |
|---|---|---|
| Extraction, grounding, evidence highlights | **Yes** | The core value |
| Review queue | **Yes** | Responsibility and quality |
| Delay, cap and cash-flow calculations | **Yes** | The numbers clients ask for |
| Obligation alerts and email | **Yes** | Prevents missed deadlines |
| Buyer assistant with refusals | **Yes** | The buyer-facing benefit |
| Database and file storage | **Yes** | A product must keep its data |
| Arabic and English UI | **Yes** for the UAE market | The audience reads Arabic |
| Statute gap packs | Valuable, **needs lawyer review** | Differentiator, with risk until reviewed |
| Monte Carlo, cross-document graph, accuracy page | Optional depth | Useful in a demo, not essential on day one |
| **Power Automate flow** | **Optional** | The app can email directly; a flow only helps Microsoft 365 clients |
| **Copilot Studio agent** | **Optional** | The web chat already answers; Teams is one more channel |
| WhatsApp, F&O, Dataverse, Power BI | **Not building** | Not needed for this use case |

## 8. Honest limitations

- The rule packs are not lawyer-reviewed, and the refusal wording needs legal sign-off.
- Extraction accuracy is measured on a small labelled set. Scanned or unusual PDFs need more testing.
- The language model can still be wrong. That is why grounding and human review exist.
- Arabic text needs review by a native speaker before real buyers see it.
- Real buyer sign-in (their own identity, not a shared key) is the next step for production.
- The model runs on a shared company key with a call cap. Heavy use needs a budget.

## 9. How to describe it to a client in one minute

"Upload a sale agreement. In about a minute you get every key term with the exact page and quote, a delay-compensation
figure calculated by tested code, a list of deadlines with alerts, and a buyer assistant that answers only from the
buyer's own contract and refuses legal questions. Anything uncertain goes to your reviewer first. Nothing is guessed,
and every number can be checked on the page."

## 10. Build order from here

1. Document (this file), reviewed by you.
2. Supabase schema script and a storage layer in the app, with mocked tests.
3. A live connection check you run once the project exists.
4. Buyer assignment table, replacing the hard-coded buyer keys.
5. Direct email sending so the product works without Power Automate; the flow stays optional.
6. Deployment settings, a clean setup guide and a demo script.
