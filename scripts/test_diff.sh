echo "123 ./shared/a.py" > a.txt
echo "124 ./shared/b.py" >> a.txt

echo "123 ./shared/a.py" > b.txt
echo "125 ./shared/b.py" >> b.txt
echo "126 ./shared/c.py" >> b.txt

diff a.txt b.txt | grep -E '^[<>]' | sed 's/^< /[-] /; s/^> /[+] /'
