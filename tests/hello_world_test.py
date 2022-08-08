import src.hello_world


def test_hello_world(capsys):
    src.hello_world.main()
    captured = capsys.readouterr()
    assert captured.out == "Hello world!\n"
