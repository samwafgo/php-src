/* Integer and overflow behavior of the exact Zend macro, including aliasing. */
#include <limits.h>
#include <stdio.h>
#include "Zend/zend_multiply.h"

static int check(long a, long b)
{
    union { long l; double d; } result;
    long overflow, aliased=a;
    double d=0;
    __int128 expected=(__int128)a * (__int128)b;
    int outside=expected > LONG_MAX || expected < LONG_MIN;
    ZEND_SIGNED_MULTIPLY_LONG(a,b,result.l,result.d,overflow);
    if (!!overflow != outside || (!outside && result.l!=(long)expected) ||
        (outside && result.d!=(double)a*(double)b)) return 1;
    ZEND_SIGNED_MULTIPLY_LONG(aliased,b,aliased,d,overflow);
    if (!!overflow != outside || (!outside && aliased!=(long)expected) ||
        (outside && d!=(double)a*(double)b)) return 2;
    return 0;
}

int main(void)
{
    long edges[]={LONG_MIN,LONG_MIN+1,-3037000500L,-3037000499L,-2,-1,0,1,2,
                  3037000499L,3037000500L,LONG_MAX-1,LONG_MAX};
    unsigned long i,j,state=0x9e3779b97f4a7c15UL;
    for(i=0;i<sizeof(edges)/sizeof(edges[0]);i++)
        for(j=0;j<sizeof(edges)/sizeof(edges[0]);j++)
            if(check(edges[i],edges[j])) return 1;
    for(i=0;i<10000;i++) {
        long a,b;
        state^=state<<13;state^=state>>7;state^=state<<17;a=(long)state;
        state^=state<<13;state^=state>>7;state^=state<<17;b=(long)state;
        if(check(a,b) || check(a,0) || check(a,1) || check(a,-1)) return 2;
    }
    puts("Zend multiply: 169 edge pairs + 40000 random/identity cases PASS");
    return 0;
}
