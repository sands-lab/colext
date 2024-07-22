#!/bin/bash

echo "Restarting jtop"
jetson_hosts=$(mk get nodes | egrep "(jao|jon|jn|jxn).+" | awk '{print $1}')

for jetson in $jetson_hosts; do
    ssh $jetson -- sudo systemctl restart jtop &
done
wait
echo "jtop restarted"