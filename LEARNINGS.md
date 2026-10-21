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

### [2026-10-21 09:39] Mål: Please design a presentation about what a Transitional Service Agreement (TSA).
- **Huvudinsikt / Pareto-härdad lösning:** {
  "title": "Mastering Transitional Service Agreements (TSA): Framework, Execution & Exit",
  "target_audience": "C-suite, M&A Project Leaders, Legal & Integration Teams",
  "slides": [
    {
      "slide_number": 1,
      "title": "Executive Summary & What is a TSA?",
      "content": [
        "D...
- **Reflektionsnotis:** Den tidigare lösningen saknade specifik struktur och detaljeringsgrad för ett professionellt M&A-sammanhang. En presentation om Transitional Service Agreements (TSA) riskerar att bli för abstrakt om den inte täcker legala, operativa, finansiella och ...

### [2026-10-21 10:09] Mål: Vad är huvudsyftet med en bloom filter?
- **Huvudinsikt / Pareto-härdad lösning:** Huvudsyftet med ett Bloomfilter är att minneseffektivt och snabbt kontrollera om ett element kan finnas i en mängd. Det ger svaret ”definitivt inte med” eller ”möjligen med”. Falska positiva kan förekomma, så ”möjligen med” kan kräva en exakt kontroll. Det används exempelvis för att undvika onödiga...
- **Reflektionsnotis:** Förslaget saknar en faktisk förklaring och kan därför inte bedömas sakligt. Förbättringen anger huvudsyftet och den centrala begränsningen: falska positiva är möjliga, men falska negativa uppstår inte vid korrekt användning....

### [2026-10-21 10:12] Mål: Vad är huvudsyftet med en bloom filter?
- **Huvudinsikt / Pareto-härdad lösning:** Huvudsyftet med ett Bloomfilter är att snabbt och minnessnålt testa om ett element kan tillhöra en mängd, så att kostsamma uppslag kan undvikas när elementet säkert saknas.

Ett standard-Bloomfilter lagrar en bitvektor, inte själva elementen. Vid insättning sätter flera hashfunktioner utvalda bitar....
- **Reflektionsnotis:** Lösningen är redan tekniskt korrekt och bemöter huvuddelen av kritiken. Svagheten är främst att huvudsyftet kommer sent och att mekanik och exempel gör svaret onödigt långt. Den förbättrade lösningen prioriterar syftet och behåller de avgörande garan...
- **Identifierade fallgropar:**
  * Vanliga felpåståenden om Bloomfilter:

- **”Ett positivt svar bevisar medlemskap.”** Nej. Det betyder att elementet *kan finnas*; falska positiva är m
