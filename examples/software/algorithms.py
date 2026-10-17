"""Measured comparison counts, never wall-clock timings."""
import random

def insertion(values):
    a=values.copy();count=0
    for i in range(1,len(a)):
        x=a[i];j=i-1
        while j>=0:
            count+=1
            if a[j]<=x:break
            a[j+1]=a[j];j-=1
        a[j+1]=x
    return a,count

def merge(values):
    if len(values)<=1:return values,0
    left,c1=merge(values[:len(values)//2]);right,c2=merge(values[len(values)//2:])
    merged=[];i=j=0;c=c1+c2
    while i<len(left) and j<len(right):
        c+=1
        if left[i]<=right[j]:merged.append(left[i]);i+=1
        else:merged.append(right[j]);j+=1
    return merged+left[i:]+right[j:],c

def benchmark(inputs, *, seed):
    rng=random.Random(seed)
    vals=[rng.randint(-100000,100000) for _ in range(inputs['n'])]
    alg=inputs['algorithm']
    sorted_values,count=(merge(vals) if alg=='merge' else insertion(vals))
    assert sorted_values==sorted(vals), 'algorithm produced incorrect results'
    return {'comparisons':count,'correct':True}
