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
