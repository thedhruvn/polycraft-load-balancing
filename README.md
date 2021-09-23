# Polycraft Load Balancer

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

