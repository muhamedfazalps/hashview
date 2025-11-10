#!/bin/bash

SSH_CONFIG="$HOME/.ssh/config"
SCREEN_NAME="hashview-agent"
REMOTE_DIR="/opt/hashview-agent"
REMOTE_CMD="python3 ./hashview-agent.py --debug"

# Extract all unique host aliases (excluding wildcards and Match blocks)
HOSTS=$(grep -E '^Host\s+' "$SSH_CONFIG" | grep -vE '[*?]|Match' | awk '{for(i=2;i<=NF;i++)print $i}')

for HOST in $HOSTS; do
  echo "Connecting to $HOST..."

  ssh "$HOST" bash -c "'
    # Check if screen is installed
    if ! command -v screen &> /dev/null; then
      echo \"screen not installed on \$HOST\"
      exit 1
    fi

    # Check for existing screen session
    if screen -list | grep -q \"$SCREEN_NAME\"; then
      echo \"Session $SCREEN_NAME already running on $HOST\"
    else
      if [[ "$HOST" == "inmannis" ]]; then 
          echo \"Removing card 0 from rotaton on inmannis\"
	  nvidia-smi -i 00000000:3D:00.0 -pm 0
	  nvidia-smi drain --pciid 0000:3D:00.0 --modify 1
	  nvidia-smi drain -p 0000:3D:00.0 --remove
	  nvidia-smi -pm 1
      fi
      #if [[ "$HOST" == "acidburn" ]]; then
          #echo \"Removing card 6 from rotation on acidburn\"
          #nvidia-smi -i 0000:41:00.0 --persistence-mode 0
	  #nvidia-smi -i 0000:04:00.0 --presistence-mode 0
	  #nvidia-smi drain --pciid 0000:04:00.0 --modify 1
          #nvidia-smi drain --pciid 0000:41:00.0 --modify 1
          #nvidia-smi --persistence-mode 1
      #fi
      echo \"Starting new screen session on $HOST\"
      screen -dmS $SCREEN_NAME bash -c \"cd $REMOTE_DIR && $REMOTE_CMD\"
    fi
  '"

  echo "Finished $HOST"
done

