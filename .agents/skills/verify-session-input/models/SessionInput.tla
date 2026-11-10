---------------------------- MODULE SessionInput ----------------------------
VARIABLES phase, expired, frameMatches, sentExpired, sentStale
vars == <<phase, expired, frameMatches, sentExpired, sentStale>>
Init == /\ phase = "Observed" /\ expired = FALSE /\ frameMatches = TRUE
        /\ sentExpired = FALSE /\ sentStale = FALSE
ExpireBeforeCheck == /\ phase = "Observed" /\ ~expired /\ expired' = TRUE
                     /\ UNCHANGED <<phase, frameMatches, sentExpired, sentStale>>
NewObservation == /\ phase \in {"Observed", "Checked"} /\ frameMatches /\ frameMatches' = FALSE
                  /\ UNCHANGED <<phase, expired, sentExpired, sentStale>>
CheckAccepted == /\ phase = "Observed" /\ ~expired /\ frameMatches /\ phase' = "Checked"
                 /\ UNCHANGED <<expired, frameMatches, sentExpired, sentStale>>
CheckRejected == /\ phase = "Observed" /\ (expired \/ ~frameMatches) /\ phase' = "Blocked"
                 /\ UNCHANGED <<expired, frameMatches, sentExpired, sentStale>>
PublishQuickly == /\ phase = "Checked" /\ phase' = "Published"
                  /\ UNCHANGED <<expired, frameMatches, sentExpired, sentStale>>
PublishAtDeadline == /\ phase = "Checked" /\ phase' = "Published" /\ expired' = TRUE
                     /\ UNCHANGED <<frameMatches, sentExpired, sentStale>>
RecheckRejected == /\ phase = "Published" /\ (expired \/ ~frameMatches) /\ phase' = "Blocked"
                   /\ UNCHANGED <<expired, frameMatches, sentExpired, sentStale>>
SendInput == /\ phase = "Published" /\ ~expired /\ frameMatches /\ phase' = "Sent"
             /\ sentExpired' = expired /\ sentStale' = ~frameMatches
             /\ UNCHANGED <<expired, frameMatches>>
PostInputCheck == /\ phase = "Sent" /\ phase' = IF expired THEN "Timeout" ELSE "Done"
                  /\ UNCHANGED <<expired, frameMatches, sentExpired, sentStale>>
Done == /\ phase \in {"Blocked", "Timeout", "Done"} /\ UNCHANGED vars
Next == ExpireBeforeCheck \/ NewObservation \/ CheckAccepted \/ CheckRejected
        \/ PublishQuickly \/ PublishAtDeadline \/ RecheckRejected \/ SendInput \/ PostInputCheck \/ Done
TypeOK == /\ phase \in {"Observed", "Checked", "Published", "Blocked", "Sent", "Timeout", "Done"}
          /\ expired \in BOOLEAN /\ frameMatches \in BOOLEAN
          /\ sentExpired \in BOOLEAN /\ sentStale \in BOOLEAN
NoInputAfterDeadline == ~sentExpired
NoStaleFrameInput == ~sentStale
=============================================================================
