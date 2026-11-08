# 02 — Creating the corral runners, original code: four personas, one name, three silently overwritten, claude-haiku-4-5

you › create a persona marathon runner waiting in a Staten Island start corral at the NYC Marathon, practical and mid-pack, who forgot sunscreen

stage › Created Marcus Chen (runner) — Mid-pack marathoner mentally calculating SPF regret strategies.                           
  · wrote temp\marcus-chen.md

you › create a persona runner in the same NYC Marathon corral who asks everyone their pace and gossips about the earlier corrals

stage › Created Marcus Chen (runner) — Chatty marathon veteran obsessed with pace comparisons and corral drama.                  
  · wrote temp\marcus-chen.md

you › create a persona runner in the same NYC Marathon corral who brought glitter instead of sunscreen and is there for a good time

stage › Created Marcus Chen (runner) — Exuberant first-time marathoner prioritizing vibes over preparation.                      
  · wrote temp\marcus-chen.md

you › create a persona first-time marathoner in the same NYC Marathon corral who is nervous and keeps asking when the corral closes

stage › Created Marcus Chen (runner) — Anxious first-time marathoner obsessing over logistics and timing.                        
  · wrote temp\marcus-chen.md

you › list personas

stage › 1 persona(s) in temp:                                                                                                    

 • Marcus Chen (runner) — Anxious first-time marathoner obsessing over logistics and timing.                             

you › 

NEXT ERROR - showing that each runner was the same person - Each persona is written in a separate API call with the same instructions, and the model has no idea which names it already used. So every call landed on the same “realistic full name”: Marcus Chen.
The code overwrote the file without warning. The filename comes from the name (marcus-chen.md), and save_persona overwrites whatever is already there.