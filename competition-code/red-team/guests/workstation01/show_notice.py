"""Root-owned fixed helper, executed only after dropping to the desktop UID."""
import fcntl,os,subprocess,sys,time
def main():
    if os.geteuid()!=1000:raise ValueError('Desktop UID required')
    expires=float(sys.argv[1])
    if not time.time()<expires<=time.time()+15:return
    # This user-owned lock is opened only after privilege drop.
    with open('/run/user/1000/summit-caldera-notice.lock','w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        if time.time()>=expires:return
        subprocess.run(['/usr/bin/zenity','--info','--title=Summit CCDC Exercise','--text=RED TEAM WAS HERE',
          '--ok-label=Dismiss','--no-wrap','--width=420'],check=False)
if __name__=='__main__':main()
