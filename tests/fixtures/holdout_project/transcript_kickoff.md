Meridian kickoff — 2026-09-07, 45 min
Attending: Dana (PM), Rob (backend), Yuki (mobile), Sofia (design), Tom (QA),
plus Gerald from Meridian IT.

Dana: main goal today is sequencing. Gerald, the auth question first.
Gerald: our policy is everything goes through our Entra tenant. I can't
approve anything until I see the integration design doc.
Dana: ok — decision then, we go Entra ID for both apps, no custom accounts.
Gerald: right. Send me the design doc and I'll take it to the security board.
Dana: Rob, can you write that integration design doc by next Friday?
Rob: yes, I'll have it out by the 18th.
Sofia: I need the work-order field list before I can finish the technician
flow mocks. Who owns that?
Dana: that's mine, I'll get you the field list Wednesday.
Yuki: flagging now — I can't start the offline sync work until someone
decides the conflict policy. Last-write-wins vs dispatcher-wins changes the
whole data model. I'm blocked on that decision.
Dana: noted. That's a real blocker and honestly I don't know who decides it —
probably needs Meridian ops in the room. Parking it for now.
Tom: do we have test devices? The fleet standard is those rugged Samsungs.
Dana: good point. Yuki, order two of the rugged units for the test bench —
new work, put it through the board.
Yuki: will do.
Dana: last thing — decision on the pilot: Northeast region only, 12 techs,
nothing ships wider without their sign-off. That's from the contract.
