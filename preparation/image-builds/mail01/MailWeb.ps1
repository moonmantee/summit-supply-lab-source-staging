if(-not('MailWeb' -as [type])){Add-Type -TypeDefinition @'
using System;
using System.Net;
using System.IO;
public static class MailWeb {
 public static string Read(string uri,string thumbprint) {
  Uri u=new Uri(uri);if(u.Scheme!="https"||u.Host!="webmail.corp.summit.test")throw new Exception("Unexpected webmail origin");
  ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
  HttpWebRequest r=(HttpWebRequest)WebRequest.Create(u);r.Timeout=20000;r.AllowAutoRedirect=false;
  r.ServerCertificateValidationCallback=(sender,cert,chain,errors)=> cert!=null&&cert.GetCertHashString().Equals(thumbprint,StringComparison.OrdinalIgnoreCase);
  using(HttpWebResponse response=(HttpWebResponse)r.GetResponse()) {
   string body=new StreamReader(response.GetResponseStream()).ReadToEnd();
   return ((int)response.StatusCode).ToString()+"\n"+(response.Headers["Location"]??"")+"\n"+body;
  }
 }
}
'@}
