# Match Maker

Tool to pair together matching meshes based on surface area and point of center. 

To try out in maya copy the matchmaker.py file into scripts folder,
then in maya write
```
import matchmaker as mm
reload(mm)

matchMakeUI = mm.ui()
```
into the script editor and if you care to, add to shelf

Larger numbers will of course take a bit longer to process but matching ~700 low poly items to ~1500
takes an average 4.7 seconds for me.
