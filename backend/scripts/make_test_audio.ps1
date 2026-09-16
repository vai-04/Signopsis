# Generates synthetic test clips with the built-in Windows voices (free, offline).
# Run from Windows PowerShell:  powershell -File backend\scripts\make_test_audio.ps1
# Output: data\clips\one_speaker.wav, data\clips\two_speakers.wav  (16 kHz mono 16-bit)
Add-Type -AssemblyName System.Speech
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$out = Join-Path $root "data\clips"
New-Item -ItemType Directory -Force $out | Out-Null

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name }
Write-Host "Voices:" ($voices -join ", ")
if ($voices.Count -lt 2) { Write-Warning "Only one voice installed; two_speakers.wav will use the same voice twice." }
$a = $voices[0]; $b = if ($voices.Count -gt 1) { $voices[1] } else { $voices[0] }
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)

function Save($path, $turns) {
  $pb = New-Object System.Speech.Synthesis.PromptBuilder
  foreach ($t in $turns) {
    $pb.StartVoice($t[0]); $pb.AppendText($t[1]); $pb.EndVoice()
    $pb.AppendBreak([TimeSpan]::FromMilliseconds(1200))
  }
  $synth.SetOutputToWaveFile($path, $fmt)
  $synth.Speak($pb)
  $synth.SetOutputToNull()
  Write-Host "wrote $path"
}

Save (Join-Path $out "one_speaker.wav") @(
  ,@($a, "Good morning. The meeting starts at ten o'clock in room four.")
  ,@($a, "Please bring your notes and the latest budget report.")
  ,@($a, "Can you tell me where the nearest pharmacy is?")
)

Save (Join-Path $out "two_speakers.wav") @(
  ,@($a, "Hi, thanks for coming in today. How are you feeling?")
  ,@($b, "Much better, thank you. The new medicine seems to be working.")
  ,@($a, "That's great to hear. Have you had any side effects?")
  ,@($b, "A little dizziness in the morning, but it goes away quickly.")
  ,@($a, "Okay. Let's keep the same dose and check again next week.")
  ,@($b, "Sounds good. Should I book the appointment at the front desk?")
)
$synth.Dispose()
