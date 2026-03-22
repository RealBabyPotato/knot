# dist sys class 4 - scaling & stuff

## Scaling Concepts
*   **Horizontal vs Vertical Scaling:**
    *   **Vertical:** bigger box (expensive af, eventually hits a ceiling).
    *   **Horizontal:** more boxes (harder to manage but infinite?).
*   **Stateless vs Stateful:**
    *   If the server doesn't remember who u are, scaling is easy.
    *   Sticky sessions are a "band-aid" - avoid them if possible.

## Load Balancers
*   Round robin (simple)
*   Least connections (smarter?)
*   IP hash (good for sticky stuff i think)

## CAP Theorem
*   **C**onsistency, **A**vailability, **P**artition Tolerance.
*   Pick 2. u literally cannot have all 3.
*   Most web stuff picks A and P.
*   Relational DBs (postgres) love C.

## Notes & Reminders
*   **NOTE:** check out "The Fallacies of Distributed Computing" later. sounds important for the exam.
*   **TODO:** ask prof about "eventual consistency" vs "strong consistency" - seems like a gray area.
*   **Reminder:** project helios deadline is friday. need to link this scaling stuff to the backend architecture for the dashboard.
*   **Side note:** my laptop is dying. need to bring a charger next time.

<details>
<summary>Raw Archive</summary>

# dist sys class 4 - scaling & stuff

- horizontal vs vertical scaling again.
- vertical = bigger box (expensive af, eventually hits a ceiling).
- horizontal = more boxes (harder to manage but infinite?).
- stateless vs stateful. if the server doesn't remember who u are, scaling is easy.
- sticky sessions are a "band-aid" - avoid them if possible.

- NOTE: check out "The Fallacies of Distributed Computing" later. sounds important for the exam.

- Load balancers:
    - round robin (simple)
    - least connections (smarter?)
    - IP hash (good for sticky stuff i think)

- side note: my laptop is dying. need to bring a charger next time.

- CAP theorem:
    - Consistency, Availability, Partition Tolerance.
    - Pick 2. u literally cannot have all 3.
    - Most web stuff picks A and P.
    - relational DBs (postgres) love C.

- TODO: ask prof about "eventual consistency" vs "strong consistency" - seems like a gray area.
- reminder: project helios deadline is friday. need to link this scaling stuff to the backend architecture for the dashboard.

</details>
