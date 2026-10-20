# M Í M I R // Vishetens Minnesbank & Cumulative Learnings

Detta dokument är Mimers beständiga minnesbank vid Mimisbrunnr. Här ackumuleras beprövade arkitekturmönster, undvikna fallgropar (Red-Team) och kärnheuristiker över tid och mellan körningar.

## 1. Verifierade Kärnheuristiker
- **Evidence Contracts:** Förankra alltid påståenden med hashade rådata/testresultat (SHA256) för att stoppa hallucinationskaskader genom agentträdet.
- **Kahn DAG Integritet:** Validera acyklisk struktur vid runtime med Kahn's algoritm för att garantera att dynamiska underuppgifter inte låser schemaläggaren.
- **Prompt-as-a-Variable:** Skicka aldrig rå kontextmättnad mellan modeller; använd versionshanterade Blackboard-deltan.
- **Käll-Agnostik:** Välj informationskanaler dynamiskt baserat på domän (GitHub/RFCs för kod, arXiv/PubMed för forskning, officiella specifikationer för protokoll).
- **JEV Grenbeskärning:** Beskär tidigt bort deluppgifter med låg Joint Expected Value ($JEV < 0.30$) för att spara latens och beräkningskostnad.
- **GEPA Pareto-Härdning:** Låt alltid en motståndaragent (Red-Team) formulera skarp kritik som sedan muterar och härdar slutlösningen längs Pareto-fronten.

## 2. Red-Team Fallgropar & Motåtgärder (Anti-Patterns)
- **Överkonfidensfällan:** Små modeller rapporterar ofta hög konfidens trots logiska fel. Förlita dig aldrig på självskattad konfidens utan oberoende kontraktverifiering.
- **Deadlock via ohanterade fel:** Om en nod kraschar måste dess underordnade beroenden omedelbart kaskaderas till `CANCELLED` för att förhindra trådlåsning.
- **Kontext-Mättnad (Context Pollution):** Skicka inte hela föregående konversationshistorik till mikromodeller. Isolera exekveringen till strikt typade input-variabler.
- **TTL-Drift & Race Conditions:** Vid asynkron distribuerad exekvering måste lås och leasing förnyas aktivt för att förhindra split-brain.

## 3. Logg över Ackumulerade Lärdomar
*(Mímir lägger automatiskt till nya härdade lärdomar här efter varje genomfört uppdrag)*

---
### [Exempel] Mål: Robust distribuerad rate limiting med Redis och Token Bucket
- **Huvudinsikt / Pareto-härdad lösning:** Implementera rate limiting via atomära Lua-skript i Redis snarare än multipla round-trips för att eliminera race conditions under hög last. Använd millisekund-precision och fallback till lokal minnesbucket vid Redis timeout.
- **Reflektionsnotis:** Den initiala lösningen saknade hantering av klock-drift mellan servrar och riskerade att blockera trafik vid tillfälliga nätverkstoppar mot cache-klustret.
- **Identifierade fallgropar:**
  * Risk för split-brain vid Redis failover om replication sker asynkront utan strikt konsensus.
