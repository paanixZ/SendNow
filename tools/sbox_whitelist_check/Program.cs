using Sandbox;
var path = args[0];
using var ac = new AccessControl();
using var input = File.OpenRead(path);
var result = ac.VerifyAssembly(input, out var trusted);
Console.WriteLine($"success={result.Success}");
foreach (var e in result.Errors) Console.WriteLine($"error: {e}");
foreach (var w in result.WhitelistErrors) Console.WriteLine($"whitelist: {w.Name} at {string.Join(", ", w.Locations.Select(l => l.ToString()))}");
return result.Success ? 0 : 1;
