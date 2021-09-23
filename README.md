# Polycraft Load Balancer

###AutoUpdating Capabilities:
- Lobby server has a script in the ~/scripts/ping_load_balancer.sh file that monitors the active branch for updates every 60 seconds 
in a cronjob and runs the update scripts
- This update impacts the lobby server, the lobby server Load Balancer, the Node Servers, and the Node Server load balancer listener.


###Updating The Git Branch:
- change configs/azurebatch.cfg (see gitBranch)
- Point the Load Balancer Server to the new branch to see the updates and deploy to all nodes.
- Note: you may need to also update the batch pool name so that all nodes are redeployed properly using the new branch.

###Updating File Share Folder:
- Update configs/azurebatch.cfg
- update run_polycraft_no_pp.sh, last line (best.default.directory)
 
###Updating default minecraft server files:
- add a file to the "uploads" folder or update a file there.
- All files in the uploads folder will overwrite similarly named files in the oxygen/ root folder on each node.
- Note: currently, this does NOT affect the lobby server.

###Update Minecraft Mod:
- just upload new jar file to the mods/ folder. remove any existing jars.
- Add a new mod (i.e., worldedit?)? just copy-pasta to that folder.
- Note: this WILL AFFECT the Lobby Server, too!

###Update Lobby Server Settings:
- change parameters in the scripts/run_polycraft_lobby.sh to adjust the VM flags that are passed in to the lobby server VM