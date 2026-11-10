---------------------------- MODULE MirrorSettlement ----------------------------
EXTENDS Naturals
VARIABLES scenario, phase, cleared, selected, requests, payments, acknowledged, returned, claimed
vars == <<scenario, phase, cleared, selected, requests, payments, acknowledged, returned, claimed>>
Scenarios == {"normal", "keep", "noClear", "noReceipt", "noReturn", "stuckSubmit",
              "weeklyNone", "weeklyOne", "weeklyAll", "stuckWeekly", "returnedWithoutReceipt"}
InitialSelected == IF scenario \in {"weeklyNone", "weeklyOne", "weeklyAll", "stuckWeekly"} THEN 3 ELSE 0
Desired == IF scenario = "weeklyOne" THEN 1 ELSE IF scenario = "weeklyAll" THEN selected ELSE 0
Init == /\ scenario \in Scenarios /\ phase = "Observe" /\ cleared = FALSE
        /\ selected = InitialSelected /\ requests = 0 /\ payments = 0
        /\ acknowledged = FALSE /\ returned = FALSE /\ claimed = FALSE
ObserveCompletion == /\ phase = "Observe" /\ phase' = "Ready" /\ cleared' = (scenario # "noClear")
                     /\ UNCHANGED <<scenario, selected, requests, payments, acknowledged, returned, claimed>>
KeepRewards == /\ phase = "Ready" /\ cleared /\ scenario = "keep" /\ phase' = "Done"
               /\ UNCHANGED <<scenario, cleared, selected, requests, payments, acknowledged, returned, claimed>>
MissingCompletion == /\ phase = "Ready" /\ ~cleared /\ phase' = "Failed"
                     /\ UNCHANGED <<scenario, cleared, selected, requests, payments, acknowledged, returned, claimed>>
RequestWeeklyChange == /\ phase = "Ready" /\ cleared /\ scenario # "keep" /\ selected > Desired
                       /\ phase' = "WaitingWeekly" /\ requests' = requests + 1
                       /\ UNCHANGED <<scenario, cleared, selected, payments, acknowledged, returned, claimed>>
ObserveWeeklyDecrease == /\ phase = "WaitingWeekly" /\ scenario # "stuckWeekly"
                         /\ phase' = "Ready" /\ selected' = selected - 1
                         /\ UNCHANGED <<scenario, cleared, requests, payments, acknowledged, returned, claimed>>
WeeklyUnchanged == /\ phase = "WaitingWeekly" /\ scenario = "stuckWeekly" /\ phase' = "Failed"
                   /\ UNCHANGED <<scenario, cleared, selected, requests, payments, acknowledged, returned, claimed>>
SubmitModules == /\ phase = "Ready" /\ cleared /\ scenario # "keep" /\ selected <= Desired
                 /\ phase' = "Submitted" /\ payments' = payments + 1
                 /\ UNCHANGED <<scenario, cleared, selected, requests, acknowledged, returned, claimed>>
ObserveReceipt == /\ phase = "Submitted" /\ scenario \notin {"noReceipt", "stuckSubmit", "returnedWithoutReceipt"}
                  /\ phase' = "Receipt"
                  /\ UNCHANGED <<scenario, cleared, selected, requests, payments, acknowledged, returned, claimed>>
SubmissionUnconfirmed == /\ phase = "Submitted" /\ scenario \in {"noReceipt", "stuckSubmit"}
                         /\ phase' = "Failed"
                         /\ UNCHANGED <<scenario, cleared, selected, requests, payments, acknowledged, returned, claimed>>
ReturnWithoutReceipt == /\ phase = "Submitted" /\ scenario = "returnedWithoutReceipt"
                        /\ phase' = "Failed" /\ returned' = TRUE
                        /\ UNCHANGED <<scenario, cleared, selected, requests, payments, acknowledged, claimed>>
AcknowledgeReceipt == /\ phase = "Receipt" /\ phase' = "Returning" /\ acknowledged' = TRUE
                      /\ UNCHANGED <<scenario, cleared, selected, requests, payments, returned, claimed>>
ObserveEntrance == /\ phase = "Returning" /\ scenario # "noReturn"
                   /\ phase' = "Done" /\ returned' = TRUE /\ claimed' = TRUE
                   /\ UNCHANGED <<scenario, cleared, selected, requests, payments, acknowledged>>
ReturnUnconfirmed == /\ phase = "Returning" /\ scenario = "noReturn" /\ phase' = "Failed"
                     /\ UNCHANGED <<scenario, cleared, selected, requests, payments, acknowledged, returned, claimed>>
Done == /\ phase \in {"Done", "Failed"} /\ UNCHANGED vars
Next == ObserveCompletion \/ KeepRewards \/ MissingCompletion \/ RequestWeeklyChange \/ ObserveWeeklyDecrease
        \/ WeeklyUnchanged \/ SubmitModules \/ ObserveReceipt \/ SubmissionUnconfirmed \/ ReturnWithoutReceipt
        \/ AcknowledgeReceipt \/ ObserveEntrance \/ ReturnUnconfirmed \/ Done
TypeOK == /\ scenario \in Scenarios
          /\ phase \in {"Observe", "Ready", "WaitingWeekly", "Submitted", "Receipt", "Returning", "Done", "Failed"}
          /\ cleared \in BOOLEAN /\ selected \in 0..3 /\ requests \in 0..3 /\ payments \in 0..2
          /\ acknowledged \in BOOLEAN /\ returned \in BOOLEAN /\ claimed \in BOOLEAN
NoRepeatedPayment == payments <= 1
NoUnauthorizedPayment == payments > 0 => (cleared /\ scenario # "keep")
WeeklyChangeNeedsObservation == requests <= InitialSelected - selected + 1
WeeklyChoiceBeforePayment == payments > 0 => selected <= Desired
ClaimNeedsReceiptAndReturn == claimed => (cleared /\ payments = 1 /\ acknowledged /\ returned)
=============================================================================
