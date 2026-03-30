from pyalex import Works

title = "You’ll never walk alone: Modeling social behavior for multi-target tracking"
res1 = Works().search(title).get()

title2 = title.replace('’', "'")
res2 = Works().search(title2).get()

title3 = title.replace('’', '').replace(':', '').replace('-', ' ')
res3 = Works().search(title3).get()

res4 = Works().filter(title_search=title2).get()

with open('test_alex_output.txt', 'w') as f:
    f.write(f"res1 (original): {len(res1)}\n")
    f.write(f"res2 (straight quote): {len(res2)}\n")
    f.write(f"res3 (no punctuation): {len(res3)}\n")
    f.write(f"res4 (title filter): {len(res4)}\n")
    if res2:
        f.write(f"res2 top title: {res2[0].get('title')}\n")
    if res3:
        f.write(f"res3 top title: {res3[0].get('title')}\n")
    if res4:
        f.write(f"res4 top title: {res4[0].get('title')}\n")
