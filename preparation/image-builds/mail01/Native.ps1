if(-not('ForumNative' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Principal;
public static class ForumNative {
 [DllImport("Netapi32.dll", CharSet=CharSet.Unicode)] static extern int NetUserGetInfo(string server,string user,int level,out IntPtr info);
 [DllImport("Netapi32.dll")] static extern int NetApiBufferFree(IntPtr ptr);
 [DllImport("Netapi32.dll", CharSet=CharSet.Unicode)] static extern int NetLocalGroupGetMembers(string server,string group,int level,out IntPtr buffer,int max,out int read,out int total,IntPtr resume);
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct USER_INFO_1 { public string name;public string password;public uint age;public uint priv;public string home;public string comment;public uint flags;public string script; }
 [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)] public static extern bool LogonUser(string user,string domain,string password,int type,int provider,out IntPtr token);
 [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
 public static int UserFlags(string user) {IntPtr ptr;int code=NetUserGetInfo(null,user,1,out ptr);if(code==2221)return -1;if(code!=0)throw new Exception("NetUserGetInfo: "+code);try{return (int)((USER_INFO_1)Marshal.PtrToStructure(ptr,typeof(USER_INFO_1))).flags;}finally{NetApiBufferFree(ptr);}}
 public static string[] GroupSids(string group) {IntPtr ptr;int read,total;int code=NetLocalGroupGetMembers(null,group,0,out ptr,-1,out read,out total,IntPtr.Zero);if(code!=0)throw new Exception("NetLocalGroupGetMembers: "+code);try{List<string> ids=new List<string>();for(int i=0;i<read;i++)ids.Add(new SecurityIdentifier(Marshal.ReadIntPtr(ptr,i*IntPtr.Size)).Value);return ids.ToArray();}finally{NetApiBufferFree(ptr);}}
 public static bool Authenticate(string user,string domain,string password,int type) {IntPtr token;if(!LogonUser(user,domain,password,type,0,out token))return false;CloseHandle(token);return true;}
 public static bool CanOpen(string user,string domain,string password,string path,System.IO.FileAccess access) {IntPtr token;if(!LogonUser(user,domain,password,2,0,out token))throw new Exception("Test identity cannot authenticate");try{using(WindowsImpersonationContext ctx=WindowsIdentity.Impersonate(token)){try{using(var s=new System.IO.FileStream(path,System.IO.FileMode.Open,access,System.IO.FileShare.ReadWrite)){return true;}}catch(UnauthorizedAccessException){return false;}}}finally{CloseHandle(token);}}
 public static bool SaveUnchanged(string user,string domain,string password,string path) {IntPtr token;if(!LogonUser(user,domain,password,2,0,out token))throw new Exception("Test identity cannot authenticate");try{using(WindowsImpersonationContext ctx=WindowsIdentity.Impersonate(token)){byte[] bytes=System.IO.File.ReadAllBytes(path);using(var s=new System.IO.FileStream(path,System.IO.FileMode.Open,System.IO.FileAccess.ReadWrite,System.IO.FileShare.Read)){s.Write(bytes,0,bytes.Length);s.SetLength(bytes.Length);}return true;}}finally{CloseHandle(token);}}
}
'@
}
if(-not('MailAccess' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
public static class MailAccess {
 [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool LogonUser(string user,string domain,string password,int type,int provider,out IntPtr token);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr token);
 public static bool CreateFile(string user,string domain,string password,string directory) {
  IntPtr token;if(!LogonUser(user,domain,password,2,0,out token))throw new Exception("Cannot authenticate test identity");
  string file=Path.Combine(directory,"owned-access-test-"+Guid.NewGuid().ToString("N")+".txt");
  try{using(WindowsImpersonationContext context=WindowsIdentity.Impersonate(token)){
   try{using(FileStream stream=new FileStream(file,FileMode.CreateNew,FileAccess.Write)){stream.WriteByte(0);}File.Delete(file);return true;}
   catch(UnauthorizedAccessException){return false;}
  }}finally{CloseHandle(token);}
 }
}
'@
}
